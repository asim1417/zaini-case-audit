#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
audit_zaini_case.py
====================
نظام فحص آلي ومنهجي لمستندات قضية زيني (الدعوى رقم 42824717).

تنبيه قانوني إلزامي:
    كل ما ينتجه هذا السكريبت هو [مخرج آلي / Script Output - سماوي] ويحتاج إلى
    [مخرج آلي يحتاج مراجعة بشرية - وردي]. لا يُعد أي مخرج رأياً قانونياً نهائياً،
    ولا يجوز اعتماده قانونياً إلا بعد مراجعة بشرية صريحة.

أنماط التشغيل:
    1) وضع البيانات المرحّلة (الافتراضي في هذه البيئة):
        يقرأ مخرجات زحف Google Drive التي تم تجهيزها عبر أدوات MCP إلى:
            <staging>/parts/*.jsonl   (بيانات وصفية لكل ملف/مجلد، سطر JSON لكل عنصر)
            <staging>/text/<id>.txt   (النص المستخرج لكل ملف قابل للقراءة)
        الاستخدام:
            python3 audit_zaini_case.py --staging <مسار مجلد staging>

    2) وضع مجلد محلي (الوضع المتصوَّر أصلاً عند توفّر مجلد Drive محلياً/مُصدَّراً):
        يمشي على مجلد محلي recursively ويقرأ PDF/DOCX/XLSX/CSV/TXT/صور.
            python3 audit_zaini_case.py --root <مسار مجلد محلي>

المخرجات تُكتب جميعها داخل مجلد zaini_case_audit_output فقط.
لا يُعدّل/يحذف/ينقل/يعيد تسمية أي ملف من المصدر.
"""

import argparse
import csv
import json
import logging
import os
import re
import sys
import unicodedata
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

# ---------------------------------------------------------------------------
# المسارات الأساسية
# ---------------------------------------------------------------------------
SCRIPT_DIR = Path(__file__).resolve().parent
OUTPUT_ROOT = SCRIPT_DIR.parent  # zaini_case_audit_output
OUT_CSV = OUTPUT_ROOT / "outputs" / "csv"
OUT_XLSX = OUTPUT_ROOT / "outputs" / "excel"
OUT_MD = OUTPUT_ROOT / "outputs" / "markdown"
OUT_JSON = OUTPUT_ROOT / "outputs" / "json"
OUT_LOGS = OUTPUT_ROOT / "logs"
OUT_UNREADABLE = OUTPUT_ROOT / "unreadable"
DEFAULT_STAGING = OUTPUT_ROOT / "staging"

for d in (OUT_CSV, OUT_XLSX, OUT_MD, OUT_JSON, OUT_LOGS, OUT_UNREADABLE):
    d.mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------------------------
# الوسوم والألوان (حسب مواصفات المهمة)
# ---------------------------------------------------------------------------
TAG_SCRIPT = "[مخرج آلي / Script Output - سماوي]"
TAG_NEEDS_REVIEW = "[مخرج آلي يحتاج مراجعة بشرية - وردي]"

# ألوان موضوعية (HEX لتلوين خلايا Excel)
COLORS = {
    "واقعة قانونية": "ADD8E6",        # أزرق فاتح
    "نتيجة قانونية": "C6EFCE",        # أخضر
    "توصية": "FFD7A8",                # برتقالي
    "مخاطر/إشكال/تعارض": "FFC7CE",    # أحمر
    "دليل/مستند": "E4C7F0",           # بنفسجي
    "دفع قانوني": "BFBFBF",           # رمادي داكن
    "مستند ناقص/يلزم تدعيم": "D2B48C",# بني
    "إحالة نظامية": "FFF2CC",         # أصفر فاتح
    "إحالة قضائية": "DDEBF7",         # أزرق رمادي
    # وسوم السكريبت
    "SCRIPT": "B7E9F7",               # سماوي
    "NEEDS_REVIEW": "FCE4EC",         # وردي
    "HEADER": "1F4E78",               # أزرق داكن للعناوين
}

# ---------------------------------------------------------------------------
# المعطيات المرجعية للقضية (تُستخدم للمطابقة فقط، وليست حصراً)
# ---------------------------------------------------------------------------
CASE_NUMBERS_KNOWN = ["42824717"]

# أرقام الصكوك/الأحكام المذكورة في التكليف (للبحث الموجَّه) + ما يُكتشف آلياً
DEED_NUMBERS_KNOWN = [
    "4431025114", "4530241622", "4530828230",
    "4630548401", "4731721487", "4731982616",
]

# الأطراف الرئيسية (الاسم الظاهر -> أنماط مطابقة بعد التطبيع)
PARTIES = {
    "عدنان زيني": ["عدنان", "عدنان احمد عباس زيني", "عدنان احمد عباس"],
    "أسامة زيني": ["اسامة احمد عباس زيني", "اسامة احمد", "اسامة زيني", "اسامة"],
    "أحمد زيني (المورّث)": ["احمد عباس زيني", "احمد زيني", "الشيخ احمد زيني"],
    "عاتقة الحرازي": ["عاتقة", "عاتقة الحرازي", "عاتقة محمد يحيى محمد علي الحرازي", "الحرازي"],
}

# أطراف/وكلاء/خبراء محتملون إضافيون (أنماط مطابقة)
OTHER_ACTORS = {
    "تركي بن رابح المطيري (وكيل)": ["تركي بن رابح", "تركي بن رابح بن سعد المطيري", "المطيري"],
    "محمد الثعلي (وكيل)": ["محمد الثعلي", "الثعلي"],
    "د. محمد البنا": ["محمد البنا", "البنا"],
    "المحامي الشهري": ["الشهري"],
    "القاضي الزايدي": ["الزايدي"],
    "القاضي اللحيدان": ["اللحيدان"],
    "شركة أمان الامتثال": ["امان الامتثال", "أمان الامتثال"],
    "د. عاصم الفارسي": ["عاصم الفارسي", "الفارسي"],
}

# الشركة محل النزاع
COMPANY_PATTERNS = ["شركة احمد زيني التجارية", "احمد زيني التجارية"]

# المحاكم والدوائر
COURTS = {
    "المحكمة التجارية بجدة": ["المحكمة التجارية بجدة", "المحكمة التجارية"],
    "محكمة الاستئناف / دائرة الاستئناف": ["محكمة الاستئناف", "دائرة الاستئناف", "الاستئناف"],
    "الدائرة الأولى التجارية": ["الدائرة الاولى التجارية", "الدائرة الاولى"],
    "المحكمة العامة بجدة": ["المحكمة العامة بجدة", "المحكمة العامة"],
    "ديوان المظالم": ["ديوان المظالم", "المظالم"],
    "التفتيش القضائي": ["التفتيش القضائي"],
    "المحكمة العليا": ["المحكمة العليا"],
}

# كلمات مفتاحية لأسماء الأنظمة (إحالات نظامية)
LAW_NAME_KEYWORDS = [
    "نظام المرافعات الشرعية", "نظام المحاكم التجارية", "نظام الشركات",
    "نظام المرافعات", "اللائحة التنفيذية", "نظام الاثبات", "نظام الإثبات",
    "نظام التنفيذ", "النظام الاساسي للحكم", "نظام القضاء",
]

# ---------------------------------------------------------------------------
# تصنيف نوع المستند (مبدئي) حسب كلمات في الاسم/النص
# ---------------------------------------------------------------------------
DOC_TYPE_RULES = [
    ("حكم / صك", ["صك حكم", "حكم نهائي", "صك", "حكم", "الولاية", "رفض الالتماس", "رفض النقض"]),
    ("عقد / اتفاقية", ["عقد بيع", "عقد", "اتفاقية", "تنازل", "ملحق تنازل", "تأسيس"]),
    ("تقرير خبرة", ["تقرير محاسبي", "تقييم", "تقرير خبرة", "خبير", "تقدير"]),
    ("تقرير طبي", ["تقرير طبي", "طبي", "الاهلية", "الأهلية", "إدراك", "ادراك"]),
    ("وكالة", ["وكالة", "توكيل"]),
    ("محضر", ["محضر", "ضبط الجلسات", "محضر ضبط", "ضبط جلسه", "ضبط الجلسه", "ضبط جلسة"]),
    ("مذكرة قضائية", ["مذكرة", "التماس", "نقض", "اعتراض", "لائحة اعتراضية", "دفاع"]),
    ("شكوى", ["شكوى", "بلاغ"]),
    ("إخطار مطالبة", ["اخطار", "إخطار", "مطالبة", "انذار", "إنذار"]),
    ("مستند مالي", ["مصروفات", "حساب", "كشف حساب", "سداد", "مالي", "فاتورة"]),
    ("مراسلة", ["ايميل", "إيميل", "خطاب", "مراسلة", "بريد", "رسالة"]),
    ("دراسة قانونية", ["دراسة", "مذكرة قانونية"]),
    ("صحيفة دعوى", ["صحيفة دعوى", "صحيفة الدعوى", "لائحة دعوى"]),
]

# كلمات تصنيف المقاطع
SEGMENT_RULES = {
    "واقعة قانونية": ["بتاريخ", "تقدم", "اقام الدعوى", "أقام الدعوى", "توفي", "اشترى",
                       "باع", "وقع", "ابرم", "أبرم", "تم البيع", "حرر", "استلم", "الورثة"],
    "نتيجة قانونية": ["حكمت", "قررت الدائرة", "تقرر", "قضت", "ثبت لدى", "رفض", "قبول",
                       "الزام", "إلزام", "بطلان", "رد الدعوى", "تأييد الحكم", "نقض الحكم"],
    "توصية": ["نوصي", "يوصى", "يُوصى", "يقترح", "يُقترح", "التوصية", "ينبغي", "نقترح", "يُنصح"],
    "دفع قانوني": ["دفع", "الدفع", "ندفع", "يدفع", "ندفع ب", "استدلال", "نستند", "نتمسك", "الدفوع"],
    "مخاطر/إشكال/تعارض": ["تعارض", "تناقض", "اشكال", "إشكال", "خطر", "يخشى", "خلل",
                            "تضارب", "غموض", "نقص", "لم يُرفق", "لم يرفق"],
    "إحالة نظامية": ["نظام", "المادة", "اللائحة", "اللائحه", "النظام"],
    "إحالة قضائية": ["حكم رقم", "صك رقم", "الدائرة", "الاستئناف", "سابقة قضائية", "المبدأ القضائي"],
    "دليل/مستند": ["مرفق", "مستند", "صورة", "نسخة", "مشفوع", "بموجب", "سند"],
}

# ---------------------------------------------------------------------------
# تطبيع النص العربي
# ---------------------------------------------------------------------------
ARABIC_INDIC = "٠١٢٣٤٥٦٧٨٩"
PERSIAN_INDIC = "۰۱۲۳۴۵۶۷۸۹"
DIGIT_MAP = {ord(c): str(i) for i, c in enumerate(ARABIC_INDIC)}
DIGIT_MAP.update({ord(c): str(i) for i, c in enumerate(PERSIAN_INDIC)})

TATWEEL = "ـ"
DIACRITICS = re.compile(r"[ً-ْٰٓ-ٟ]")
PRESENTATION_FORM = re.compile(r"[ﭐ-﷿ﹰ-﻿]")


def to_ascii_digits(text):
    return text.translate(DIGIT_MAP)


def normalize_arabic(text):
    """تطبيع: توحيد الهمزات والألف والياء، إزالة التطويل والتشكيل، تحويل الأرقام."""
    if not text:
        return ""
    # NFKC يحوّل الأشكال التقديمية (presentation forms) إلى حروف عربية قياسية
    text = unicodedata.normalize("NFKC", text)
    text = to_ascii_digits(text)
    text = DIACRITICS.sub("", text)
    text = text.replace(TATWEEL, "")
    # توحيد الألف
    text = re.sub("[إأآا]", "ا", text)
    text = text.replace("ى", "ي")
    text = text.replace("ؤ", "و").replace("ئ", "ي").replace("ء", "")
    text = text.replace("ة", "ه")
    text = re.sub(r"\s+", " ", text)
    return text


def normalize_term(term):
    return normalize_arabic(term)


def make_haystack(norm_text):
    """يبني نصاً للبحث يشمل الاتجاه الأمامي والمعكوس (لمعالجة نصوص OCR ذات الترتيب البصري)."""
    return norm_text + " " + norm_text[::-1]


def presentation_ratio(raw_text):
    if not raw_text:
        return 0.0
    pf = len(PRESENTATION_FORM.findall(raw_text))
    letters = sum(1 for c in raw_text if c.isalpha())
    return (pf / letters) if letters else 0.0


# ---------------------------------------------------------------------------
# دوال الاستخراج
# ---------------------------------------------------------------------------
RE_LONG_NUM = re.compile(r"\b\d{6,}\b")
RE_HIJRI = re.compile(r"\b1[34]\d{2}\s*[/\-]\s*\d{1,2}\s*[/\-]\s*\d{1,2}\b"
                      r"|\b\d{1,2}\s*[/\-]\s*\d{1,2}\s*[/\-]\s*1[34]\d{2}\b")
RE_GREG = re.compile(r"\b(?:19|20)\d{2}\s*[/\-]\s*\d{1,2}\s*[/\-]\s*\d{1,2}\b"
                     r"|\b\d{1,2}\s*[/\-]\s*\d{1,2}\s*[/\-]\s*(?:19|20)\d{2}\b")
RE_AMOUNT = re.compile(r"(\d[\d.,٬]{2,})\s*(?:ريال|ريالا|ر\.س|ر\.?س\.?)")
RE_AMOUNT2 = re.compile(r"(?:مبلغ|قدره|وقدره|بمبلغ|قيمته|بقيمة)\s*([0-9][\d.,٬]{2,})")
RE_ARTICLE = re.compile(r"الماده\s*(?:رقم\s*)?\(?\s*(\d{1,3})\)?"
                        r"|ماده\s*(?:رقم\s*)?\(?\s*(\d{1,3})\)?")


def find_terms(haystack, patterns):
    hits = []
    for p in patterns:
        np = normalize_term(p)
        if np and np in haystack:
            hits.append(p)
    return hits


def extract_entities(raw_text):
    """يستخرج الكيانات القانونية من نص ملف واحد. يعيد قاموساً من القوائم."""
    norm = normalize_arabic(raw_text)
    hay = make_haystack(norm)
    ents = {
        "parties": [], "other_actors": [], "company": [],
        "case_numbers": [], "deed_numbers_known": [], "long_numbers": [],
        "hijri_dates": [], "greg_dates": [], "amounts": [],
        "courts": [], "law_names": [], "articles": [],
    }

    # الأطراف
    for label, pats in PARTIES.items():
        if find_terms(hay, pats):
            ents["parties"].append(label)
    for label, pats in OTHER_ACTORS.items():
        if find_terms(hay, pats):
            ents["other_actors"].append(label)
    if find_terms(hay, COMPANY_PATTERNS):
        ents["company"].append("شركة أحمد زيني التجارية")

    # أرقام القضايا والصكوك (تُستخرج من النص الأمامي - الأرقام لا تُعكس عادةً)
    for cn in CASE_NUMBERS_KNOWN:
        if cn in norm:
            ents["case_numbers"].append(cn)
    for dn in DEED_NUMBERS_KNOWN:
        if dn in norm:
            ents["deed_numbers_known"].append(dn)
    # أرقام طويلة (6 خانات فأكثر) كمؤشرات لصكوك/سجلات/قضايا تحتاج مراجعة
    longs = set(RE_LONG_NUM.findall(norm))
    ents["long_numbers"] = sorted(longs)

    # التواريخ
    ents["hijri_dates"] = sorted(set(m.group(0).strip() for m in RE_HIJRI.finditer(norm)))
    ents["greg_dates"] = sorted(set(m.group(0).strip() for m in RE_GREG.finditer(norm)))

    # المبالغ (مع توحيد الصيغة وإزالة التكرار والضجيج)
    raw_amounts = []
    for m in RE_AMOUNT.finditer(norm):
        raw_amounts.append((m.group(1), m.group(0)))
    for m in RE_AMOUNT2.finditer(norm):
        raw_amounts.append((m.group(1), m.group(0)))
    canon = {}
    for num, ctx in raw_amounts:
        digits = re.sub(r"[^\d]", "", num)
        has_mag = bool(re.search(r"(مليون|ملايين|الف|آلاف|مليار)", norm[max(0, norm.find(ctx)):norm.find(ctx) + len(ctx) + 12])) if ctx in norm else False
        # تجاهل الأرقام الصغيرة جداً ما لم تُرفق بوحدة (مليون/ألف)
        if len(digits) < 4 and not has_mag:
            continue
        if len(digits) > 13:  # أرقام شاذة (غالباً التصاق OCR) - تُستبعد
            continue
        disp = format(int(digits), ",") if digits else num
        canon[digits] = disp
    ents["amounts"] = [canon[k] for k in sorted(canon, key=lambda d: int(d), reverse=True)]

    # المحاكم
    for label, pats in COURTS.items():
        if find_terms(hay, pats):
            ents["courts"].append(label)

    # الأنظمة
    ents["law_names"] = find_terms(hay, LAW_NAME_KEYWORDS)
    arts = set()
    for m in RE_ARTICLE.finditer(norm):
        arts.add(next(g for g in m.groups() if g))
    ents["articles"] = sorted(arts, key=lambda x: int(x))

    return ents, norm


# كلمات عامة جداً لا يُعتمد عليها إلا في العنوان (تظهر في جسم معظم الوثائق القضائية)
_GENERIC_BODY_STOP = {"حكم", "صك", "عقد", "دفاع", "طبي", "حساب", "مالي", "خطاب", "دراسة"}


def classify_doc_type(title, norm_text):
    """التصنيف يعتمد أساساً على عنوان الملف (عناوين هذه القضية وصفية ودقيقة)،
    ثم يلجأ إلى جسم النص بكلمات محددة فقط (يستبعد الكلمات العامة جداً)."""
    title_hay = normalize_arabic(title)
    for label, kws in DOC_TYPE_RULES:
        if find_terms(title_hay, kws):
            return label
    if norm_text:
        body_hay = make_haystack(norm_text)
        for label, kws in DOC_TYPE_RULES:
            specific = [k for k in kws if k not in _GENERIC_BODY_STOP]
            if specific and find_terms(body_hay, specific):
                return label
    return "غير مصنف"


def classify_segments(norm_text):
    """تصنيف على مستوى الملف: أي فئات مقاطع ظهرت + الكلمة المفتاحية المطابِقة."""
    if not norm_text:
        return {}
    hay = make_haystack(norm_text)
    found = {}
    for cat, kws in SEGMENT_RULES.items():
        hits = find_terms(hay, kws)
        if hits:
            found[cat] = hits
    return found


# ---------------------------------------------------------------------------
# قراءة الملفات المحلية (وضع --root)
# ---------------------------------------------------------------------------
READABLE_EXT = {".pdf", ".docx", ".doc", ".xlsx", ".xls", ".csv", ".txt"}
IMAGE_EXT = {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".tif", ".tiff"}


def read_local_file(path, logger, missing_deps):
    ext = path.suffix.lower()
    try:
        if ext == ".txt":
            return path.read_text(encoding="utf-8", errors="replace"), "ok", None
        if ext == ".csv":
            return path.read_text(encoding="utf-8", errors="replace"), "ok", None
        if ext == ".docx":
            try:
                import docx
            except ImportError:
                missing_deps.add("python-docx")
                return "", "error", "python-docx غير مثبتة"
            d = docx.Document(str(path))
            return "\n".join(p.text for p in d.paragraphs), "ok", None
        if ext in (".xlsx", ".xls"):
            try:
                import openpyxl
            except ImportError:
                missing_deps.add("openpyxl")
                return "", "error", "openpyxl غير مثبتة"
            wb = openpyxl.load_workbook(str(path), read_only=True, data_only=True)
            parts = []
            for ws in wb.worksheets:
                for row in ws.iter_rows(values_only=True):
                    parts.append(" ".join(str(c) for c in row if c is not None))
            return "\n".join(parts), "ok", None
        if ext == ".pdf":
            try:
                import pypdf
            except ImportError:
                missing_deps.add("pypdf")
                return "", "error", "pypdf غير مثبتة"
            reader = pypdf.PdfReader(str(path))
            txt = "\n".join((pg.extract_text() or "") for pg in reader.pages)
            if len(txt.strip()) < 20:
                return txt, "empty", "نص ضئيل - يُحتمل أن الملف صورة ممسوحة يحتاج OCR"
            return txt, "ok", None
        if ext in IMAGE_EXT:
            return "", "needs_ocr", "ملف صورة - يحتاج OCR"
        return "", "error", f"امتداد غير مدعوم: {ext}"
    except Exception as e:  # noqa
        return "", "error", f"{type(e).__name__}: {e}"


def page_count_local(path):
    try:
        if path.suffix.lower() == ".pdf":
            import pypdf
            return len(pypdf.PdfReader(str(path)).pages)
    except Exception:  # noqa
        return None
    return None


# ---------------------------------------------------------------------------
# تحميل السجلات (وضع --staging أو --root)
# ---------------------------------------------------------------------------
def load_from_staging(staging_dir, logger):
    # فضّل الفهرس النظيف الموحّد إن وُجد (parts_clean)، وإلا استخدم parts
    clean = Path(staging_dir) / "parts_clean"
    parts_dir = clean if (clean.exists() and any(clean.glob("*.jsonl"))) else Path(staging_dir) / "parts"
    text_dir = Path(staging_dir) / "text"
    records = []
    seen_ids = set()
    # خريطة معرّف المجلد -> عنوانه (لتحويل parentId إلى مسار مقروء) إن توفّرت
    folder_map = {}
    fm_path = Path(staging_dir) / "study" / "folder_map.json"
    if fm_path.exists():
        try:
            folder_map = json.loads(fm_path.read_text(encoding="utf-8"))
        except Exception as e:  # noqa
            logger.warning("تعذّر قراءة folder_map.json: %s", e)
    if not parts_dir.exists():
        logger.error("مجلد parts غير موجود: %s", parts_dir)
        return records
    for jl in sorted(parts_dir.glob("*.jsonl")):
        with open(jl, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError as e:
                    logger.warning("سطر JSON غير صالح في %s: %s", jl.name, e)
                    continue
                rid = rec.get("id")
                if rid and rid in seen_ids:
                    continue  # تجنّب التكرار عبر الدفعات
                if rid:
                    seen_ids.add(rid)
                rec["_source_part"] = jl.name
                # حوّل parentId/parent_path إلى عنوان مجلد مقروء إن أمكن
                pp = rec.get("parent_path") or ""
                if pp in folder_map:
                    rec["parent_path"] = folder_map[pp]
                elif (not pp or pp == rec.get("parentId")) and rec.get("parentId") in folder_map:
                    rec["parent_path"] = folder_map[rec.get("parentId")]
                # حمّل النص إن وُجد
                rec["_text"] = ""
                tf = rec.get("text_file")
                if tf and Path(tf).exists():
                    try:
                        rec["_text"] = Path(tf).read_text(encoding="utf-8", errors="replace")
                    except Exception as e:  # noqa
                        logger.warning("تعذّر قراءة %s: %s", tf, e)
                elif rec.get("id"):
                    cand = text_dir / f"{rec['id']}.txt"
                    if cand.exists():
                        rec["_text"] = cand.read_text(encoding="utf-8", errors="replace")
                records.append(rec)
    logger.info("حُمِّل %d سجل من %s", len(records), parts_dir)
    return records


def load_from_root(root_dir, logger, missing_deps):
    root = Path(root_dir)
    records = []
    for p in sorted(root.rglob("*")):
        is_folder = p.is_dir()
        rel_parent = str(p.parent.relative_to(root)) if p.parent != root else root.name
        rec = {
            "id": str(p.relative_to(root)),
            "title": p.name,
            "mimeType": "folder" if is_folder else "",
            "fileExtension": p.suffix.lstrip(".").lower() if not is_folder else None,
            "fileSize": (p.stat().st_size if not is_folder else None),
            "createdTime": datetime.fromtimestamp(p.stat().st_ctime).isoformat() if not is_folder else None,
            "modifiedTime": datetime.fromtimestamp(p.stat().st_mtime).isoformat() if not is_folder else None,
            "viewUrl": str(p),
            "owner": None,
            "parentId": str(p.parent.relative_to(root)) if p.parent != root else "",
            "parent_path": rel_parent,
            "is_folder": is_folder,
            "_source_part": "local_walk",
        }
        if is_folder:
            rec.update({"text_chars": None, "text_file": None,
                        "read_status": None, "read_error": None, "_text": ""})
        else:
            txt, status, err = read_local_file(p, logger, missing_deps)
            rec.update({
                "text_chars": len(txt), "text_file": str(p) if status == "ok" else None,
                "read_status": status, "read_error": err, "_text": txt,
                "_page_count": page_count_local(p),
            })
        records.append(rec)
    logger.info("مُشي على %d عنصر تحت %s", len(records), root)
    return records


# ---------------------------------------------------------------------------
# كتابة المخرجات
# ---------------------------------------------------------------------------
def try_import_pandas(missing_deps):
    try:
        import pandas as pd  # noqa
        return pd
    except ImportError:
        missing_deps.add("pandas")
        return None


def write_csv(path, header, rows):
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(header)
        for r in rows:
            w.writerow(r)


def write_excel_sheets(xlsx_path, sheets, missing_deps, color_col=None):
    """sheets: list of (sheet_name, header, rows). يكتب Excel مع تلوين العناوين والوسوم."""
    try:
        import openpyxl
        from openpyxl.styles import Font, PatternFill, Alignment
    except ImportError:
        missing_deps.add("openpyxl")
        return False
    wb = openpyxl.Workbook()
    wb.remove(wb.active)
    header_fill = PatternFill("solid", fgColor=COLORS["HEADER"])
    header_font = Font(bold=True, color="FFFFFF")
    for name, header, rows in sheets:
        safe_name = re.sub(r"[\\/*?:\[\]]", "-", name)[:31]
        ws = wb.create_sheet(title=safe_name)
        ws.sheet_view.rightToLeft = True
        ws.append(header)
        for c in ws[1]:
            c.fill = header_fill
            c.font = header_font
            c.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        for r in rows:
            ws.append(["" if v is None else v for v in r])
        # تلوين حسب عمود الفئة/اللون إن وُجد
        if color_col and color_col in header:
            ci = header.index(color_col)
            for row in ws.iter_rows(min_row=2):
                val = str(row[ci].value or "")
                hexc = None
                for key, hx in COLORS.items():
                    if key in val:
                        hexc = hx
                        break
                if hexc:
                    fill = PatternFill("solid", fgColor=hexc)
                    for cell in row:
                        cell.fill = fill
        # عرض الأعمدة
        for i, _ in enumerate(header, 1):
            ws.column_dimensions[openpyxl.utils.get_column_letter(i)].width = 26
    wb.save(xlsx_path)
    return True


# ---------------------------------------------------------------------------
# المنطق الرئيسي
# ---------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser(description="فحص آلي لمستندات قضية زيني 42824717")
    ap.add_argument("--staging", help="مسار مجلد staging (وضع البيانات المرحّلة من Drive)")
    ap.add_argument("--root", help="مسار مجلد محلي للمشي عليه recursively")
    ap.add_argument("--case-folder-name", default="مستندات قضية 42824717",
                    help="اسم مجلد القضية كما في Drive")
    args = ap.parse_args()

    # السجلّ
    log_path = OUT_LOGS / "audit_run.log"
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=[logging.FileHandler(log_path, encoding="utf-8"),
                  logging.StreamHandler(sys.stdout)],
    )
    logger = logging.getLogger("audit")
    logger.info("=== بدء تشغيل الفحص الآلي %s ===", TAG_SCRIPT)

    missing_deps = set()
    # تحقق من المكتبات الاختيارية لـ OCR
    try:
        import pytesseract  # noqa
        import PIL  # noqa
        ocr_available = True
    except ImportError:
        ocr_available = False
        missing_deps.add("pytesseract+Pillow (OCR)")

    # تحميل السجلات
    if args.root:
        logger.info("الوضع: مجلد محلي --root=%s", args.root)
        records = load_from_root(args.root, logger, missing_deps)
        mode = "local_root"
    else:
        staging = args.staging or str(DEFAULT_STAGING)
        logger.info("الوضع: بيانات مرحّلة --staging=%s", staging)
        records = load_from_staging(staging, logger)
        mode = "staging"

    if not records:
        logger.error("لا توجد سجلات للمعالجة. تأكد من المسار/الزحف.")

    # سجل التبعيات الناقصة
    if missing_deps:
        dep_md = OUT_LOGS / "dependencies_missing.md"
        lines = ["# مكتبات ناقصة / غير مثبتة", "", TAG_SCRIPT, "",
                 "المكتبات التالية غير متاحة في البيئة، وأُكمل العمل بما هو متاح:", ""]
        install = {
            "pandas": "pip install pandas",
            "openpyxl": "pip install openpyxl",
            "python-docx": "pip install python-docx",
            "pypdf": "pip install pypdf",
            "pytesseract+Pillow (OCR)": "pip install pytesseract pillow ; "
                                         "وتثبيت محرك tesseract-ocr مع حزمة اللغة العربية (tesseract-ocr-ara)",
        }
        for d in sorted(missing_deps):
            lines.append(f"- **{d}** — أمر التثبيت المقترح: `{install.get(d, 'pip install ' + d)}`")
        lines += ["", "> لم يُنفَّذ التثبيت تلقائياً ما لم تسمح البيئة بذلك."]
        dep_md.write_text("\n".join(lines), encoding="utf-8")
        logger.warning("مكتبات ناقصة: %s (انظر %s)", ", ".join(sorted(missing_deps)), dep_md)

    # ----------------------------------------------------------------------
    # المعالجة: استخراج وتصنيف
    # ----------------------------------------------------------------------
    files = [r for r in records if not r.get("is_folder")]
    folders = [r for r in records if r.get("is_folder")]

    inventory_rows = []
    entity_rows = []
    classified_rows = []
    law_rows = []
    unreadable_rows = []
    new_outputs_rows = []
    full_json = {"meta": {}, "files": [], "folders": []}

    agg = {
        "parties": Counter(), "other_actors": Counter(), "courts": Counter(),
        "case_numbers": Counter(), "deeds_known": Counter(), "long_numbers": Counter(),
        "amounts": Counter(), "hijri": Counter(), "greg": Counter(),
        "law_names": Counter(), "articles": Counter(), "doc_types": Counter(),
        "company": Counter(),
    }

    auto_idx = 0
    for r in files:
        title = r.get("title", "")
        raw = r.get("_text", "") or ""
        status = r.get("read_status")
        chars = r.get("text_chars")
        if chars is None:
            chars = len(raw)
        pf_ratio = presentation_ratio(raw)
        orientation = "visual/OCR-reversed" if pf_ratio > 0.15 else ("logical" if raw else "—")
        readable = bool(raw and len(raw.strip()) >= 20 and status not in ("error", "needs_ocr"))
        needs_ocr = (not readable) and (
            (r.get("fileExtension") or "").lower() in ("pdf", "jpg", "jpeg", "png", "tif", "tiff", "")
            or status in ("error", "empty", "needs_ocr")
        )

        ents, norm = extract_entities(raw) if raw else ({k: [] for k in
            ["parties","other_actors","company","case_numbers","deed_numbers_known",
             "long_numbers","hijri_dates","greg_dates","amounts","courts","law_names","articles"]}, "")
        doc_type = classify_doc_type(title, norm)
        segs = classify_segments(norm)

        # تجميع
        for x in ents["parties"]: agg["parties"][x] += 1
        for x in ents["other_actors"]: agg["other_actors"][x] += 1
        for x in ents["courts"]: agg["courts"][x] += 1
        for x in ents["case_numbers"]: agg["case_numbers"][x] += 1
        for x in ents["deed_numbers_known"]: agg["deeds_known"][x] += 1
        for x in ents["long_numbers"]: agg["long_numbers"][x] += 1
        for x in ents["amounts"]: agg["amounts"][x] += 1
        for x in ents["hijri_dates"]: agg["hijri"][x] += 1
        for x in ents["greg_dates"]: agg["greg"][x] += 1
        for x in ents["law_names"]: agg["law_names"][x] += 1
        for x in ents["articles"]: agg["articles"][x] += 1
        for x in ents["company"]: agg["company"][x] += 1
        agg["doc_types"][doc_type] += 1

        # صف الجرد
        inventory_rows.append([
            title, r.get("parent_path", ""), (r.get("fileExtension") or ""),
            r.get("mimeType", ""), r.get("fileSize", ""),
            r.get("createdTime", ""), r.get("modifiedTime", ""),
            "نعم" if readable else "لا", "نعم" if needs_ocr else "لا",
            r.get("_page_count", "") if r.get("_page_count") else "",
            chars, orientation, doc_type, status or "",
            r.get("viewUrl", ""), TAG_SCRIPT,
        ])

        # صف الكيانات
        entity_rows.append([
            title, doc_type,
            "؛ ".join(ents["parties"]),
            "؛ ".join(ents["other_actors"]),
            "؛ ".join(ents["company"]),
            "؛ ".join(ents["case_numbers"]),
            "؛ ".join(ents["deed_numbers_known"]),
            "؛ ".join(ents["long_numbers"][:25]),
            "؛ ".join(ents["hijri_dates"][:25]),
            "؛ ".join(ents["greg_dates"][:25]),
            "؛ ".join(ents["amounts"][:25]),
            "؛ ".join(ents["courts"]),
            "؛ ".join(ents["law_names"]),
            "؛ ".join(ents["articles"]),
            TAG_SCRIPT, TAG_NEEDS_REVIEW,
        ])

        # صفوف التصنيف
        for cat, kws in segs.items():
            classified_rows.append([
                title, cat, "، ".join(kws[:8]),
                orientation, r.get("parent_path", ""),
                f"{cat}", TAG_SCRIPT, TAG_NEEDS_REVIEW,
            ])

        # الإحالات النظامية (جدول التحقق الرسمي)
        for ln in ents["law_names"]:
            law_rows.append([ln, "", title, r.get("parent_path", ""),
                             "يحتاج تحقق رسمي", "هيئة الخبراء بمجلس الوزراء / جريدة أم القرى",
                             TAG_SCRIPT, TAG_NEEDS_REVIEW])
        for art in ents["articles"]:
            law_rows.append([f"إشارة إلى المادة ({art})", art, title, r.get("parent_path", ""),
                             "يحتاج تحقق رسمي", "وزارة العدل / ناجز / هيئة الخبراء",
                             TAG_SCRIPT, TAG_NEEDS_REVIEW])

        # الملفات غير المقروءة / تحتاج OCR
        if not readable:
            reason = r.get("read_error") or ("نص ضئيل/فارغ" if status == "empty" else "غير مقروء")
            unreadable_rows.append([
                title, r.get("parent_path", ""), (r.get("fileExtension") or ""),
                r.get("fileSize", ""), status or "", reason,
                "نعم" if needs_ocr else "لا",
                "OCR غير متاح في البيئة" if (needs_ocr and not ocr_available) else "",
                r.get("viewUrl", ""), TAG_SCRIPT, TAG_NEEDS_REVIEW,
            ])

        # JSON كامل
        full_json["files"].append({
            "id": r.get("id"), "title": title, "parent_path": r.get("parent_path"),
            "ext": r.get("fileExtension"), "mimeType": r.get("mimeType"),
            "size": r.get("fileSize"), "createdTime": r.get("createdTime"),
            "modifiedTime": r.get("modifiedTime"), "viewUrl": r.get("viewUrl"),
            "readable": readable, "needs_ocr": needs_ocr, "text_chars": chars,
            "orientation": orientation, "doc_type": doc_type,
            "read_status": status, "entities": ents, "segments": segs,
            "tags": [TAG_SCRIPT, TAG_NEEDS_REVIEW],
        })

    for r in folders:
        full_json["folders"].append({
            "id": r.get("id"), "title": r.get("title"),
            "parent_path": r.get("parent_path"), "viewUrl": r.get("viewUrl"),
        })

    # ----------------------------------------------------------------------
    # كشف التكرارات والأسماء المتشابهة
    # ----------------------------------------------------------------------
    by_title = defaultdict(list)
    by_size = defaultdict(list)
    for r in files:
        by_title[normalize_arabic(r.get("title", ""))].append(r.get("title"))
        sz = r.get("fileSize")
        if sz:
            by_size[str(sz)].append(r.get("title"))
    dup_rows = []
    for sz, titles in by_size.items():
        if len(titles) > 1:
            dup_rows.append([sz, " | ".join(titles), "نفس الحجم - يُحتمل تكرار",
                             TAG_SCRIPT, TAG_NEEDS_REVIEW])
    similar_rows = []
    norm_titles = list({normalize_arabic(r.get("title", "")): r.get("title")
                        for r in files}.items())
    seen = set()
    for i in range(len(norm_titles)):
        for j in range(i + 1, len(norm_titles)):
            a, ta = norm_titles[i]
            b, tb = norm_titles[j]
            if not a or not b:
                continue
            sa, sb = set(a.split()), set(b.split())
            if sa and sb:
                jac = len(sa & sb) / len(sa | sb)
                if jac >= 0.6 and (ta, tb) not in seen:
                    seen.add((ta, tb))
                    similar_rows.append([ta, tb, f"{jac:.2f}", TAG_SCRIPT, TAG_NEEDS_REVIEW])

    # ----------------------------------------------------------------------
    # المستندات الأعلى أهمية (heuristic)
    # ----------------------------------------------------------------------
    importance = []
    for fj in full_json["files"]:
        score = 0
        dt = fj["doc_type"]
        if dt in ("حكم / صك", "عقد / اتفاقية", "تقرير خبرة", "صحيفة دعوى"):
            score += 3
        if fj["entities"]["deed_numbers_known"]:
            score += 3
        if fj["entities"]["case_numbers"]:
            score += 1
        if fj["entities"]["amounts"]:
            score += 1
        score += min(len(fj["entities"]["parties"]), 3)
        if fj["readable"]:
            score += 1
        importance.append((score, fj))
    importance.sort(key=lambda x: x[0], reverse=True)
    central_rows = [[fj["title"], fj["doc_type"], score,
                     "؛ ".join(fj["entities"]["parties"]),
                     "؛ ".join(fj["entities"]["deed_numbers_known"]),
                     fj["parent_path"], TAG_SCRIPT, TAG_NEEDS_REVIEW]
                    for score, fj in importance[:25] if score >= 3]

    # ----------------------------------------------------------------------
    # المقارنة مع الدراسة (إن وُجد نص الدراسة في staging/study)
    # ----------------------------------------------------------------------
    study_dir = (Path(args.staging) if args.staging else DEFAULT_STAGING) / "study"
    study_text = ""
    if study_dir.exists():
        sf = study_dir / "study.txt"
        if sf.exists():
            study_text = sf.read_text(encoding="utf-8", errors="replace")

    # روابط الدراسة: معرّفات الملفات والعناوين المستخرجة من روابط الدراسة (إن وُجدت)
    study_file_ids, id_title_map = [], {}
    fi = study_dir / "file_ids.json"
    it = study_dir / "id_title_map.json"
    if fi.exists():
        try:
            study_file_ids = json.loads(fi.read_text(encoding="utf-8"))
        except Exception:  # noqa
            pass
    if it.exists():
        try:
            id_title_map = json.loads(it.read_text(encoding="utf-8"))
        except Exception:  # noqa
            pass

    staged_ids = {r.get("id") for r in files if r.get("id")}
    title_by_id = {r.get("id"): r.get("title") for r in files}

    in_both, in_study_only, in_drive_only = [], [], []
    if study_file_ids:
        # مقارنة موثوقة بالمعرّفات (روابط الدراسة المباشرة مقابل الملفات المُحمّلة)
        study_set = set(study_file_ids)
        for fid in sorted(study_set):
            t = title_by_id.get(fid) or id_title_map.get(fid, fid)
            if fid in staged_ids:
                in_both.append([t, t, TAG_SCRIPT, TAG_NEEDS_REVIEW])
            else:
                in_study_only.append([id_title_map.get(fid, fid),
                                      "مذكور في الدراسة برابط لكن تعذّر تحميله آلياً - يلزم تحقق",
                                      TAG_SCRIPT, TAG_NEEDS_REVIEW])
        for fid in sorted(staged_ids - study_set):
            in_drive_only.append([title_by_id.get(fid, fid),
                                  "موجود في Drive وغير مرتبط برابط في الدراسة (مبدئياً)",
                                  TAG_SCRIPT, TAG_NEEDS_REVIEW])
    elif study_text:
        # احتياط: مقارنة تقريبية بالعناوين عند غياب الروابط
        drive_titles_norm = {normalize_arabic(r.get("title", "")): r.get("title") for r in files}
        idx = [ln.strip() for ln in study_text.splitlines()
               if 6 < len(ln.strip()) < 160 and any(k in ln for k in
               ["مرفق", "صك", "عقد", "حكم", "تقرير", "وكالة", "مذكرة", "محضر", "شكوى"])]
        for s in idx:
            sn = normalize_arabic(s)
            matched = next((d for dn, d in drive_titles_norm.items()
                            if sn.split() and dn.split()
                            and len(set(sn.split()) & set(dn.split())) / len(set(sn.split()) | set(dn.split())) >= 0.45), None)
            (in_both if matched else in_study_only).append(
                [s, matched or "غير موجود (تقريبي)", TAG_SCRIPT, TAG_NEEDS_REVIEW])

    # خلاصة الدراسة الذاتية (كما وردت نصاً في الدراسة) لإدراجها في التقرير
    study_summary_lines = []
    for ln in study_text.splitlines():
        s = ln.strip()
        if any(k in s for k in ["خلاصة الفهرس", "بنداً", "بنود الدراسة",
                                "لم تذكرها", "غير موجودة في الدرايف", "192 ملفاً"]) and 10 < len(s) < 400:
            study_summary_lines.append(s)

    # ----------------------------------------------------------------------
    # كتابة CSV
    # ----------------------------------------------------------------------
    inv_header = ["اسم الملف", "المسار", "الامتداد", "النوع(MIME)", "الحجم",
                  "تاريخ الإنشاء", "تاريخ التعديل", "قابل للقراءة؟", "يحتاج OCR؟",
                  "عدد الصفحات", "عدد الأحرف", "اتجاه النص", "نوع المستند(مبدئي)",
                  "حالة القراءة", "الرابط", "الوسم"]
    write_csv(OUT_CSV / "01_full_file_inventory.csv", inv_header, inventory_rows)

    ent_header = ["اسم الملف", "نوع المستند", "الأطراف", "أطراف/وكلاء آخرون", "الشركة",
                  "أرقام القضايا", "أرقام صكوك معروفة", "أرقام طويلة(مؤشرات)",
                  "تواريخ هجرية", "تواريخ ميلادية", "مبالغ", "محاكم/دوائر",
                  "أنظمة", "مواد", "وسم آلي", "وسم مراجعة"]
    write_csv(OUT_CSV / "03_extracted_legal_entities.csv", ent_header, entity_rows)

    cls_header = ["اسم الملف", "الفئة", "كلمات مطابِقة", "اتجاه النص", "المسار",
                  "اللون/الوسم", "وسم آلي", "وسم مراجعة"]
    write_csv(OUT_CSV / "04_classified_outputs.csv", cls_header, classified_rows)

    law_header = ["الإحالة النظامية", "رقم المادة", "الملف المصدر", "المسار",
                  "الحالة", "مصدر التحقق المقترح", "وسم آلي", "وسم مراجعة"]
    write_csv(OUT_CSV / "05_official_law_verification_needed.csv", law_header, law_rows)

    unr_header = ["اسم الملف", "المسار", "الامتداد", "الحجم", "حالة القراءة",
                  "السبب", "يحتاج OCR؟", "ملاحظة OCR", "الرابط", "وسم آلي", "وسم مراجعة"]
    write_csv(OUT_CSV / "06_unreadable_or_ocr_needed.csv", unr_header, unreadable_rows)

    cmp_header_both = ["مذكور في الدراسة", "المطابق في Drive", "وسم آلي", "وسم مراجعة"]
    cmp_header_s = ["مذكور في الدراسة وغير موجود", "ملاحظة", "وسم آلي", "وسم مراجعة"]
    cmp_header_d = ["موجود في Drive وغير مذكور", "ملاحظة", "وسم آلي", "وسم مراجعة"]
    write_csv(OUT_CSV / "02a_in_both.csv", cmp_header_both, in_both)
    write_csv(OUT_CSV / "02b_in_study_only.csv", cmp_header_s, in_study_only)
    write_csv(OUT_CSV / "02c_in_drive_only.csv", cmp_header_d, in_drive_only)
    write_csv(OUT_CSV / "dup_same_size.csv",
              ["الحجم", "الملفات", "ملاحظة", "وسم آلي", "وسم مراجعة"], dup_rows)
    write_csv(OUT_CSV / "similar_names.csv",
              ["ملف 1", "ملف 2", "نسبة التشابه", "وسم آلي", "وسم مراجعة"], similar_rows)
    write_csv(OUT_CSV / "central_documents.csv",
              ["اسم الملف", "نوع المستند", "درجة الأهمية", "الأطراف",
               "صكوك معروفة", "المسار", "وسم آلي", "وسم مراجعة"], central_rows)

    # جدول مخرجات السكريبت الجديدة (لم ترد في الدراسة)
    for score, fj in importance:
        e = fj["entities"]
        if not (e["deed_numbers_known"] or e["amounts"] or e["case_numbers"]):
            continue
        auto_idx += 1
        nature = "إحالة قضائية" if fj["doc_type"] == "حكم / صك" else (
                 "دليل/مستند" if fj["doc_type"] in ("عقد / اتفاقية", "تقرير خبرة") else "واقعة")
        extracted = []
        if e["deed_numbers_known"]:
            extracted.append("صكوك: " + "، ".join(e["deed_numbers_known"]))
        if e["amounts"]:
            extracted.append("مبالغ: " + "، ".join(e["amounts"][:3]))
        if e["case_numbers"]:
            extracted.append("قضايا: " + "، ".join(e["case_numbers"]))
        new_outputs_rows.append([
            f"A{auto_idx:03d}", nature, " | ".join(extracted), fj["title"],
            fj["parent_path"], "ظهر آلياً عبر مطابقة أرقام/مبالغ في النص",
            "يحتاج مراجعة", "نعم",
            TAG_SCRIPT, "يحتمل أن يكون ذا صلة بالدراسة - يتطلب تحققاً قانونياً",
            "عرض على المحامي للمطابقة مع فهرس الدراسة",
            TAG_NEEDS_REVIEW,
        ])
    write_csv(OUT_CSV / "new_script_outputs.csv",
              ["رقم المخرج", "النوع", "النص المستخرج", "الملف المصدر", "المسار",
               "سبب الظهور الآلي", "ورد في الدراسة؟", "يحتاج مراجعة؟",
               "وسم اللون", "الأثر المحتمل", "الإجراء المقترح", "وسم مراجعة"],
              new_outputs_rows)

    # ----------------------------------------------------------------------
    # كتابة Excel
    # ----------------------------------------------------------------------
    write_excel_sheets(OUT_XLSX / "01_full_file_inventory.xlsx",
                       [("جرد الملفات", inv_header, inventory_rows)], missing_deps)
    write_excel_sheets(OUT_XLSX / "02_study_vs_drive_comparison.xlsx", [
        ("موجود في الاثنين", cmp_header_both, in_both),
        ("بالدراسة فقط", cmp_header_s, in_study_only),
        ("بـDrive فقط", cmp_header_d, in_drive_only),
        ("تكرار-نفس الحجم", ["الحجم", "الملفات", "ملاحظة", "وسم آلي", "وسم مراجعة"], dup_rows),
        ("أسماء متشابهة", ["ملف 1", "ملف 2", "نسبة التشابه", "وسم آلي", "وسم مراجعة"], similar_rows),
    ], missing_deps)
    write_excel_sheets(OUT_XLSX / "03_extracted_legal_entities.xlsx",
                       [("الكيانات القانونية", ent_header, entity_rows)], missing_deps)
    write_excel_sheets(OUT_XLSX / "04_classified_outputs.xlsx",
                       [("تصنيف المقاطع", cls_header, classified_rows)],
                       missing_deps, color_col="اللون/الوسم")
    write_excel_sheets(OUT_XLSX / "05_official_law_verification_needed.xlsx",
                       [("التحقق النظامي", law_header, law_rows)], missing_deps)
    write_excel_sheets(OUT_XLSX / "06_unreadable_or_ocr_needed.xlsx",
                       [("غير مقروء/OCR", unr_header, unreadable_rows)], missing_deps)
    write_excel_sheets(OUT_XLSX / "07_central_and_new_outputs.xlsx", [
        ("مستندات مركزية", ["اسم الملف", "نوع المستند", "درجة الأهمية", "الأطراف",
                            "صكوك معروفة", "المسار", "وسم آلي", "وسم مراجعة"], central_rows),
        ("مخرجات جديدة", ["رقم المخرج", "النوع", "النص المستخرج", "الملف المصدر", "المسار",
                          "سبب الظهور الآلي", "ورد في الدراسة؟", "يحتاج مراجعة؟",
                          "وسم اللون", "الأثر المحتمل", "الإجراء المقترح", "وسم مراجعة"],
         new_outputs_rows),
    ], missing_deps)

    # ----------------------------------------------------------------------
    # JSON كامل
    # ----------------------------------------------------------------------
    full_json["meta"] = {
        "generated_at": datetime.now().isoformat(),
        "mode": mode,
        "case_number": CASE_NUMBERS_KNOWN[0],
        "case_folder_name": args.case_folder_name,
        "counts": {
            "total_records": len(records), "files": len(files), "folders": len(folders),
            "readable": sum(1 for f in full_json["files"] if f["readable"]),
            "unreadable": sum(1 for f in full_json["files"] if not f["readable"]),
            "needs_ocr": sum(1 for f in full_json["files"] if f["needs_ocr"]),
        },
        "ocr_available": ocr_available,
        "missing_deps": sorted(missing_deps),
        "disclaimer": f"{TAG_SCRIPT} {TAG_NEEDS_REVIEW} — لا يُعد أي مخرج رأياً قانونياً نهائياً.",
        "aggregates": {k: dict(v.most_common(50)) for k, v in agg.items()},
    }
    (OUT_JSON / "full_audit_data.json").write_text(
        json.dumps(full_json, ensure_ascii=False, indent=2), encoding="utf-8")

    # ----------------------------------------------------------------------
    # قائمة unreadable كملف نصي (دون نقل الأصول)
    # ----------------------------------------------------------------------
    (OUT_UNREADABLE / "unreadable_files_list.md").write_text(
        "\n".join(["# قائمة الملفات غير المقروءة / التي تحتاج OCR", "", TAG_SCRIPT, TAG_NEEDS_REVIEW, ""]
                  + [f"- {row[0]}  — (المسار: {row[1]}) — السبب: {row[5]}" for row in unreadable_rows]),
        encoding="utf-8")

    # ----------------------------------------------------------------------
    # تقرير Markdown الأولي
    # ----------------------------------------------------------------------
    c = full_json["meta"]["counts"]
    md = []
    md.append("# تقرير الفحص الآلي الأولي لمستندات قضية زيني")
    md.append("")
    md.append(f"{TAG_SCRIPT}  {TAG_NEEDS_REVIEW}")
    md.append("")
    md.append("> **تنبيه:** جميع ما يلي مخرجات آلية أولية لا تُعد رأياً قانونياً نهائياً، "
              "وتحتاج إلى مراجعة بشرية واعتماد صريح من المحامي.")
    md.append("")
    md.append(f"- **رقم القضية:** {CASE_NUMBERS_KNOWN[0]}")
    md.append(f"- **مجلد القضية:** {args.case_folder_name}")
    md.append(f"- **تاريخ التشغيل:** {full_json['meta']['generated_at']}")
    md.append(f"- **وضع التشغيل:** {mode}")
    md.append(f"- **OCR متاح؟** {'نعم' if ocr_available else 'لا — الملفات الممسوحة تُعلَّم كـ(تحتاج OCR)'}")
    md.append("")
    md.append("## 1) ملخص تنفيذي تقني")
    md.append(f"- إجمالي العناصر المرصودة: **{c['total_records']}** (ملفات: {c['files']}، مجلدات: {c['folders']})")
    md.append(f"- ملفات مقروءة: **{c['readable']}**")
    md.append(f"- ملفات غير مقروءة: **{c['unreadable']}**")
    md.append(f"- ملفات تحتاج OCR: **{c['needs_ocr']}**")
    md.append("")
    md.append("## 2) أكثر أنواع المستندات تكراراً")
    for t, n in agg["doc_types"].most_common(15):
        md.append(f"- {t}: {n}")
    md.append("")
    md.append("## 3) أهم أرقام القضايا والصكوك المستخرجة")
    md.append("**أرقام قضايا:** " + ("، ".join(f"{k}({v})" for k, v in agg["case_numbers"].most_common()) or "—"))
    md.append("")
    md.append("**صكوك معروفة (من قائمة التكليف) ظهرت آلياً:** " +
              ("، ".join(f"{k}({v})" for k, v in agg["deeds_known"].most_common()) or "لم تظهر مطابقات مباشرة"))
    md.append("")
    md.append("**أرقام طويلة أخرى (مؤشرات صكوك/سجلات تحتاج مراجعة):** " +
              ("، ".join(f"{k}({v})" for k, v in agg["long_numbers"].most_common(20)) or "—"))
    md.append("")
    md.append("## 4) أهم الأطراف المتكررة")
    for k, v in agg["parties"].most_common():
        md.append(f"- {k}: {v}")
    for k, v in agg["other_actors"].most_common():
        md.append(f"- (طرف/وكيل) {k}: {v}")
    md.append("")
    md.append("## 5) أهم المبالغ المستخرجة (مرتّبة حسب القيمة)")

    def _amount_val(s):
        digits = re.sub(r"[^\d]", "", s)
        return int(digits) if digits else 0
    big_amounts = sorted(agg["amounts"].items(), key=lambda kv: _amount_val(kv[0]), reverse=True)
    for k, v in big_amounts[:20]:
        md.append(f"- {k} ريال (تكرار {v})")
    md.append("")
    md.append("## 6) أهم التواريخ المستخرجة")
    md.append("**هجرية:** " + ("، ".join(f"{k}({v})" for k, v in agg["hijri"].most_common(20)) or "—"))
    md.append("")
    md.append("**ميلادية:** " + ("، ".join(f"{k}({v})" for k, v in agg["greg"].most_common(20)) or "—"))
    md.append("")
    md.append("## 7) المحاكم والدوائر")
    for k, v in agg["courts"].most_common():
        md.append(f"- {k}: {v}")
    md.append("")
    md.append("## 8) جدول المستندات المركزية المحتملة")
    md.append("| الملف | النوع | الأهمية | الأطراف |")
    md.append("|---|---|---|---|")
    for row in central_rows[:20]:
        md.append(f"| {row[0]} | {row[1]} | {row[2]} | {row[3]} |")
    md.append("")
    if study_summary_lines:
        md.append("## 8-أ) خلاصة المطابقة كما وردت نصاً في الدراسة")
        md.append(f"عدد روابط ملفات الدراسة المباشرة: **{len(study_file_ids)}** ملفاً عبر 18 قسماً — "
                  f"جرى **جردها بالكامل بالمعرّفات**؛ "
                  f"استُخرج نصها آلياً: **{c['readable']}**؛ "
                  f"لم يُستخرج نصها (صور/ملفات مضغوطة/تحتاج OCR): **{c['needs_ocr']}**.")
        md.append("")
        for s in study_summary_lines[:8]:
            md.append(f"> {s}")
        md.append("")
    md.append("## 9) المستندات المذكورة في الدراسة وغير الموجودة")
    if study_text:
        for row in in_study_only[:50]:
            md.append(f"- {row[0]} — {row[1]}")
        if not in_study_only:
            md.append("- لا يوجد فرق بالمعرّفات: كل ملف ربطته الدراسة تم تحميله آلياً.")
    else:
        md.append("- **لم يُعثر على نص الدراسة** في `staging/study/`؛ لذلك لم تُجرَ مقارنة الفهرس. "
                  "يلزم تزويد ملف الدراسة لإتمام هذه المقارنة.")
    md.append("")
    md.append("## 10) المستندات الموجودة وغير المذكورة في الدراسة")
    if study_text:
        for row in in_drive_only[:80]:
            md.append(f"- {row[0]}")
    else:
        md.append("- تعذّرت المقارنة لعدم توفّر نص الدراسة (انظر القسم 9).")
    md.append("")
    md.append("## 11) جدول الإحالات النظامية التي تحتاج تحققاً رسمياً")
    md.append("| الإحالة | المادة | الملف | الحالة |")
    md.append("|---|---|---|---|")
    seen_law = set()
    for row in law_rows:
        key = (row[0], row[1])
        if key in seen_law:
            continue
        seen_law.add(key)
        md.append(f"| {row[0]} | {row[1]} | {row[2]} | {row[4]} |")
        if len(seen_law) >= 40:
            break
    md.append("")
    md.append("> لم يتم التحقق رسمياً من النصوص النظامية بسبب عدم توفّر الوصول للمصدر "
              "الرسمي في بيئة التشغيل. المصادر المقترحة: هيئة الخبراء بمجلس الوزراء، "
              "جريدة أم القرى، وزارة العدل/ناجز، المركز الوطني للوثائق والمحفوظات.")
    md.append("")
    md.append("## 12) مخرجات السكريبت الجديدة (لم ترد في الدراسة)")
    md.append(f"عدد المخرجات الآلية المرشّحة: **{len(new_outputs_rows)}** — انظر "
              "`outputs/excel/07_central_and_new_outputs.xlsx` و`outputs/csv/new_script_outputs.csv`.")
    md.append("")
    md.append("## 13) قائمة المخاطر التقنية في الفحص")
    md.append("- الوصول إلى Google Drive عبر MCP فقط (لا يوجد mount محلي)، والاستخراج تم عبر "
              "تمثيل نصي قد يكون ناقصاً للملفات الكبيرة.")
    md.append("- كثير من ملفات PDF ممسوحة ضوئياً ونصها بترتيب بصري/أشكال تقديمية (OCR)؛ "
              "المطابقة تمت على نص مطبّع في الاتجاهين، وقد تحدث مطابقات ناقصة أو زائدة.")
    md.append("- OCR محلي غير متاح؛ الملفات الصورية تُعلَّم كـ(تحتاج OCR) دون استخراج.")
    md.append("- بعض المجلدات ظهرت فارغة عبر الواجهة؛ قد يكون ذلك بسبب صلاحيات/فهرسة "
              "وليس بالضرورة خلوّها فعلياً — يلزم تأكيد بشري.")
    md.append("- استخراج المبالغ/التواريخ بالتعابير النمطية قد يلتقط أرقاماً غير ذات صلة.")
    md.append("")
    md.append("## 14) ما يحتاج مراجعة قانونية بشرية")
    md.append("- اعتماد تصنيف نوع كل مستند.")
    md.append("- التحقق من ربط الأرقام الطويلة بأرقام الصكوك/الأحكام الصحيحة.")
    md.append("- التحقق الرسمي من كل النصوص النظامية والمواد.")
    md.append("- مطابقة فهرس الدراسة مع الملفات (عند توفّر نص الدراسة).")
    md.append("- مراجعة الملفات غير المقروءة وتشغيل OCR معتمد عليها.")
    md.append("")
    md.append("---")
    md.append(f"_تم توليد هذا التقرير آلياً_ — {TAG_SCRIPT} {TAG_NEEDS_REVIEW}")
    (OUT_MD / "initial_audit_report.md").write_text("\n".join(md), encoding="utf-8")

    # ----------------------------------------------------------------------
    # قائمة مراجعة المحامي
    # ----------------------------------------------------------------------
    chk = ["# قائمة مراجعة المحامي (Human Review Checklist)", "",
           f"{TAG_SCRIPT} {TAG_NEEDS_REVIEW}", "",
           "> كل بند أدناه ناتج آلي يحتاج تأكيداً بشرياً قبل الاعتماد القانوني.", "",
           "## أ) سلامة الجرد",
           "- [ ] تأكيد العدد الكلي للملفات والمجلدات ومطابقته مع Drive.",
           "- [ ] مراجعة المجلدات التي ظهرت فارغة والتأكد من صلاحيات الوصول.",
           "", "## ب) الكيانات المستخرجة",
           "- [ ] التحقق من أسماء الأطراف والوكلاء والخبراء.",
           "- [ ] التحقق من ربط الأرقام الطويلة بأرقام صكوك/أحكام صحيحة.",
           "- [ ] التحقق من المبالغ المالية ومصادرها (تقييم/حكم/سداد).",
           "- [ ] التحقق من التواريخ الهجرية/الميلادية ومراجع كل منها.",
           "", "## ج) التصنيف",
           "- [ ] اعتماد تصنيف نوع كل مستند.",
           "- [ ] مراجعة تصنيف المقاطع (وقائع/نتائج/دفوع/مخاطر...).",
           "", "## د) الإحالات النظامية",
           "- [ ] التحقق الرسمي من كل نظام ومادة (هيئة الخبراء/أم القرى/ناجز).",
           "", "## هـ) المقارنة مع الدراسة",
           "- [ ] تزويد نص الدراسة (إن لم يُتح) لإتمام مقارنة الفهرس.",
           "- [ ] مراجعة المستندات (بالدراسة فقط) و(بـDrive فقط).",
           "", "## و) الملفات غير المقروءة",
           "- [ ] تشغيل OCR معتمد على الملفات الممسوحة.",
           "- [ ] مراجعة أي ملف فشل في القراءة.",
           "", "## ز) المخرجات الجديدة",
           "- [ ] مراجعة جدول (مخرجات السكريبت الجديدة) وتحديد أثرها على الدراسة.",
           "",
           "> لا يُستخدم وسم [مخرج آلي تم اعتماده قانونياً - أزرق داكن] إلا بعد اعتماد المحامي صراحةً."]
    (OUT_MD / "human_review_checklist.md").write_text("\n".join(chk), encoding="utf-8")

    logger.info("اكتمل الفحص. الملفات: %d، مقروء: %d، غير مقروء: %d، يحتاج OCR: %d",
                c["files"], c["readable"], c["unreadable"], c["needs_ocr"])
    logger.info("=== انتهى التشغيل ===")

    # ملخص على الشاشة
    print("\n==== ملخص الأرقام ====")
    print(json.dumps(c, ensure_ascii=False, indent=2))
    print("نوع المستندات:", dict(agg["doc_types"].most_common()))
    print("المخرجات في:", OUTPUT_ROOT / "outputs")


if __name__ == "__main__":
    main()
