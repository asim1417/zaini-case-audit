#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
improve_readability.py
يحسّن قراءة النصوص الممسوحة/المعكوسة الترتيب (OCR بترتيب بصري) — سطراً بسطر:
  - يكتشف كل سطر معكوس عبر إشارتين: (أ) وجود أشكال عربية تقديمية، أو
    (ب) غلبة كلمات مفتاحية بصيغتها المعكوسة على الصيغة الصحيحة في السطر.
  - يطبّع (NFKC) ويعكس السطر المعكوس فقط، مع إعادة عكس الأرقام/اللاتيني وإصلاح الأقواس.
  - يبقي الأسطر الصحيحة كما هي (يدعم الملفات المختلطة: جزء معكوس وجزء سليم).
  - يكتب نسخة مقروءة لكل ملف في staging/text_readable/<id>.txt (لا يلمس الأصل).
الاستخدام: python3 improve_readability.py <staging_dir>
"""
import sys
import re
import json
import unicodedata
from pathlib import Path

STAGING = Path(sys.argv[1] if len(sys.argv) > 1 else "staging")
SRC = STAGING / "text"
DST = STAGING / "text_readable"
DST.mkdir(parents=True, exist_ok=True)

PF = re.compile(r"[ﭐ-﷿ﹰ-﻿]")  # أشكال عربية تقديمية
LTR_RUN = re.compile(r"[0-9A-Za-z٠-٩@._\-/:]+")
MIRROR = {"(": ")", ")": "(", "[": "]", "]": "[", "{": "}", "}": "{",
          "<": ">", ">": "<", "«": "»", "»": "«"}

# قاموس عربي شائع (كلمات بصيغتها الصحيحة) لقياس «معقولية» اتجاه السطر
DICT = set("""في من على إلى عن مع هذا هذه التي الذي قد كما حيث أن إن ما لا قال
المدعي المدعى عليه الحكم الدعوى المحكمة الدائرة العقد البيع الشركة الحصص المبلغ
ريال تاريخ رقم صك نظام المادة الاستئناف التجارية 
الوالد المورث الثمن السداد التقرير الخبير القيمة الشيخ ضد بشأن وقد وفي ولا وهو وعن
بسم الله الرحمن الرحيم السلام عليكم ورحمة وبركاته وبعد الموضوع الطرف الاسم الصفة
الجلسة قرر قررت تقرر حكمت ثبت رفض قبول الزام بطلان تأييد نقض التماس اعتراض شكوى
الجنسية سعودي هوية وطنية مكتب المحاماة العدل وزير معالي صاحب الفضيلة أصحاب قاضي
بتاريخ خيار الغبن الورثة الوكالة التخارج تأسيس مرفق مستند صورة كشف تنفيذ مطالبة
يطلب نطلب أطلب وأن لكون لكن إذ إذا كذلك أيضا عليه عليها فيها فيه منه منها
الهوية الوطنية حاضر مدعى المهنة السجل العنوان اصالة بصفته نفسه الموكل ممثل محامي
الحاضرون الحاضر القضية المملكة العربية السعودية الصفحة الوقائع المنطوق بناء
افتتحت الجلسة وحيث الاسباب الحمد والصلاة رسول معالي رئيس المجلس الاعلى القضاء
التفتيش القضائي الشريعة المعاملات المدنية موضوع الشكوى ولي العهد حفظه سلمه
الموقر المحترم اشارة فاشارة لائحة رقابية المحاكم قضاتها الذمة ابراء الفضيلة""".split())


def _norm_word(w):
    """تطبيع خفيف لتوحيد الألف/الياء/التاء المربوطة لزيادة تغطية المطابقة."""
    w = unicodedata.normalize("NFKC", w)
    w = re.sub("[إأآ]", "ا", w).replace("ى", "ي").replace("ة", "ه")
    return w


def _load_case_terms():
    """تعلّم ذاتي: يقرأ case_config.json ويستخرج أسماء الأطراف/الوكلاء/الشركة
    تلقائياً ويضيفها لقاموس كشف الاتجاه — فيتقوّى المحرّك لكل قضية بلا ضبط يدوي."""
    import os
    candidates = []
    if os.environ.get("CASE_CONFIG"):
        candidates.append(Path(os.environ["CASE_CONFIG"]))
    if os.environ.get("CASE_ROOT"):
        candidates.append(Path(os.environ["CASE_ROOT"]) / "case_config.json")
    candidates += [STAGING.parent / "case_config.json", STAGING / "case_config.json"]
    words = set()
    for c in candidates:
        try:
            if not c.exists():
                continue
            cfg = json.loads(c.read_text(encoding="utf-8"))
        except Exception:  # noqa
            continue
        buckets = []
        for key in ("parties", "other_actors"):
            d = cfg.get(key, {})
            if isinstance(d, dict):
                for k, v in d.items():
                    buckets.append(k)
                    buckets += (v if isinstance(v, list) else [])
        buckets += cfg.get("company_patterns", []) or []
        case = cfg.get("case", {})
        buckets += [case.get("title", "")]
        for phrase in buckets:
            for tok in re.findall(r"[؀-ۿ]{3,}", _norm_word(str(phrase))):
                words.add(tok)
        break
    # أضِف المصطلحات المكتشفة تلقائياً من النص (detect_parties) إن وُجدت
    auto = STAGING / "auto_terms.json"
    try:
        if auto.exists():
            for phrase in json.loads(auto.read_text(encoding="utf-8")):
                for tok in re.findall(r"[؀-ۿ]{3,}", _norm_word(str(phrase))):
                    words.add(tok)
    except Exception:  # noqa
        pass
    return words


# للتسجيل نستخدم الكلمات المميِّزة فقط (٣ أحرف فأكثر) لتفادي المطابقات العَرَضية،
# مع إضافة مصطلحات القضية تلقائياً من الإعداد (تعلّم ذاتي لكل قضية).
_SCORE_WORDS = list({_norm_word(w) for w in DICT if len(w) >= 3} | _load_case_terms())


def line_score(s):
    s = _norm_word(s)
    return sum(s.count(w) for w in _SCORE_WORDS)


def fix_ltr_runs(s):
    return LTR_RUN.sub(lambda m: m.group(0)[::-1], s)


def reverse_line(norm_line):
    rev = norm_line[::-1]
    rev = fix_ltr_runs(rev)
    rev = "".join(MIRROR.get(c, c) for c in rev)
    return rev


ARLET = re.compile(r"[؀-ۿ]")


def collapse_doubling(line):
    """يعالج تكرار OCR المزدوج للكلمات العربية فقط (يتجنّب الأرقام والجداول):
       «كلمة كلمة» ⇐ «كلمة»، و«نصنص» (تضعيف داخل الكلمة) ⇐ «نص»."""
    toks = line.split(" ")
    out = []
    for t in toks:
        n = len(t)
        is_ar = bool(ARLET.search(t)) and not any(ch.isdigit() for ch in t)
        # تضعيف داخل الرمز (النصف الأول = النصف الثاني) — للكلمات العربية فقط
        if is_ar and n >= 6 and n % 2 == 0 and t[:n // 2] == t[n // 2:]:
            t = t[:n // 2]
        # تكرار متجاور مطابق — للكلمات العربية ذات طول معقول فقط
        if out and out[-1] == t and is_ar and len(t) >= 3:
            continue
        out.append(t)
    return " ".join(out)


def process_text(raw):
    """يختار لكل سطر الاتجاه الأعلى «معقولية»، ثم يزيل تضعيف OCR للكلمات العربية."""
    out = []
    fixed_any = False
    for line in raw.split("\n"):
        if not line.strip():
            out.append("")
            continue
        norm = unicodedata.normalize("NFKC", line)
        rev = reverse_line(norm)
        sf, sr = line_score(norm), line_score(rev)
        chosen = rev if sr > sf else norm
        if sr > sf:
            fixed_any = True
        new = collapse_doubling(chosen)
        if new != chosen:
            fixed_any = True
        out.append(new)
    return "\n".join(out), fixed_any


def main():
    fixed = copied = 0
    fixed_ids = []
    for p in sorted(SRC.glob("*.txt")):
        if p.name.startswith("_"):
            continue
        raw = p.read_text(encoding="utf-8", errors="replace")
        new, fixed_any = process_text(raw)
        (DST / p.name).write_text(new, encoding="utf-8")
        if fixed_any:
            fixed += 1
            fixed_ids.append(p.stem)
        else:
            copied += 1
    (DST / "_fixed_ids.json").write_text(json.dumps(fixed_ids, ensure_ascii=False),
                                         encoding="utf-8")
    print(f"نسخ مقروءة: {fixed + copied} (فيها أسطر صُحِّح ترتيبها: {fixed} / "
          f"سليمة كما هي: {copied})")
    print(f"المخرجات في: {DST}")


if __name__ == "__main__":
    main()
