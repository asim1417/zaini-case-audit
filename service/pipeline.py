#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
pipeline.py — تشغيل محرّك الفحص القانوني على مهمّة واحدة (مجلد رفع).

يعيد استخدام محرّك المشروع: OCR محلي معزّز لكل ملف → بناء full_documents.jsonl →
توليد الحزمة الوثائقية + الملحق المالي + التقارير، ثم ضغط النتائج.
يُستدعى من خدمة API لكل مهمّة بمعزل (CASE_ROOT خاص بكل مهمّة).
"""
import os, sys, re, copy, json, shutil, zipfile, datetime, subprocess
from pathlib import Path

# جذر المشروع ومجلد السكربتات الأصلية (المحرّك)
REPO = Path(__file__).resolve().parent.parent
ENGINE = REPO / "zaini_case_audit_output" / "scripts"
sys.path.insert(0, str(ENGINE))

from PIL import Image                     # noqa: E402
try:
    import lift_engine            # محرّك استخراج مهيكل اختياري (Datalab lift)
except Exception:
    lift_engine = None
try:
    import azure_engine           # محرّك OCR سحابي اختياري (Azure Document Intelligence)
except Exception:
    azure_engine = None
from pdf2image import convert_from_path   # noqa: E402


def _load_engine():
    import reocr_pilot, reocr_hard, audit_case, make_master_excel  # noqa
    return reocr_pilot, reocr_hard, audit_case, make_master_excel


# إعداد القضية لكل مهمّة: نحفظ القيم الافتراضية العامة مرة واحدة ثم نعيدها قبل كل
# مهمّة، فلا يتسرّب إعداد قضية سابقة إلى قضية جديدة في نفس العملية.
_CASE_KEYS = ("CASE_NUMBERS_KNOWN", "DEED_NUMBERS_KNOWN", "PARTIES", "OTHER_ACTORS",
              "COMPANY_PATTERNS", "COURTS", "CASE_TITLE", "CASE_FOLDER_NAME")
_CASE_DEFAULTS = None


def _apply_case_config(AZ, job_dir: Path, log):
    global _CASE_DEFAULTS
    if _CASE_DEFAULTS is None:
        _CASE_DEFAULTS = {k: copy.deepcopy(getattr(AZ, k)) for k in _CASE_KEYS}
    for k, v in _CASE_DEFAULTS.items():
        setattr(AZ, k, copy.deepcopy(v))
    cfg = job_dir / "case_config.json"
    if cfg.exists():
        os.environ["CASE_CONFIG"] = str(cfg)
        AZ._load_case_config()
        log("إعداد قضية مخصّص: أطراف=%d، أرقام صكوك=%d" % (len(AZ.PARTIES), len(AZ.DEED_NUMBERS_KNOWN)))
    else:
        os.environ.pop("CASE_CONFIG", None)


def run_job(job_dir: Path, log=print):
    """يعالج كل الملفات في job_dir/uploads وينتج job_dir/outputs + result.zip."""
    RP, RH, AZ, MME = _load_engine()
    _apply_case_config(AZ, job_dir, log)
    uploads = job_dir / "uploads"
    out = job_dir / "outputs"
    (out / "json").mkdir(parents=True, exist_ok=True)
    (out / "csv").mkdir(parents=True, exist_ok=True)
    today = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    recs = []
    files = sorted([p for p in uploads.iterdir() if p.is_file()])
    log("ملفات الإدخال: %d" % len(files))
    for i, f in enumerate(files, 1):
        try:
            sig = f.open("rb").read(4)
            if sig[:4] == b"%PDF":
                pages = convert_from_path(str(f), dpi=RH.DPI)
            elif sig[:3] == b"\xff\xd8\xff" or sig[:4] == b"\x89PNG":
                pages = [Image.open(f).convert("RGB")]
            else:
                log("تخطّي (نوع غير مدعوم): %s" % f.name); continue
        except Exception as e:
            log("فشل فتح %s: %s" % (f.name, e)); continue
        engine_used = "tesseract-ara-enhanced"
        full = None
        if azure_engine and azure_engine.available():     # سحابي عالي الجودة (إن فُعّل)
            atext = azure_engine.ocr_text(f)
            if atext and atext.strip():
                full = atext; engine_used = "azure-document-intelligence"
                log("azure: قراءة سحابية — %s" % f.name)
        if full is None:                                  # تراجع آمن للمحرّك المحلي
            full = "\n".join(RH.best_page_text(im)[0] for im in pages)
        title = f.name
        norm = AZ.normalize_arabic(full)
        dtype = AZ.classify_doc_type(title, norm)
        ents, _ = AZ.extract_entities(full)
        cf = {"entities": ents, "doc_type": dtype, "title": title, "viewUrl": ""}
        card = dict(MME.build_card(cf, full))
        if lift_engine and lift_engine.available():
            lc = lift_engine.card_from_lift(f)
            if lc:
                card = {**card, **lc}
                log("lift: بطاقة مُحسّنة — %s" % f.name)
        recs.append({"id": f.name, "title": title, "doc_type": dtype, "parent_path": "",
                     "viewUrl": "", "card": card, "entities": ents,
                     "readable": bool(full.strip()), "full_text": full,
                     "reocr": {"new_q": round(RP.quality_metrics(full)["quality"], 1),
                               "engine": engine_used, "dpi": RH.DPI, "date": today,
                               "replaced": True, "ingested": True}})
        log("[%d/%d] %s — %s" % (i, len(files), dtype, title[:50]))

    with (out / "json" / "full_documents.jsonl").open("w", encoding="utf-8") as g:
        for r in recs:
            g.write(json.dumps(r, ensure_ascii=False) + "\n")
    # فحص الجودة (CSV مطلوب من بعض المولّدات)
    (out / "csv" / "14_readability_qc.csv").write_text(
        "﻿الملف,الحالة,أسطر,أسطر معكوسة متبقية,نسبة عربية معقولة,عدد كلمات,النوع,القسم\n", encoding="utf-8")

    env = dict(os.environ, CASE_ROOT=str(job_dir))
    for script in ("legal_package.py", "financial_annex.py"):
        log("تشغيل %s ..." % script)
        r = subprocess.run([sys.executable, str(ENGINE / script)], env=env,
                           capture_output=True, text=True, timeout=3600)
        if r.returncode != 0:
            log("تحذير %s: %s" % (script, (r.stderr or "")[-300:]))

    # ضغط النتائج
    result = job_dir / "result.zip"
    with zipfile.ZipFile(result, "w", zipfile.ZIP_DEFLATED) as z:
        pkg = out / "package"
        if pkg.exists():
            for p in pkg.rglob("*"):
                if p.is_file():
                    zi = zipfile.ZipInfo(str(p.relative_to(out)))
                    zi.flag_bits |= 0x800
                    z.writestr(zi, p.read_bytes())
    log("اكتملت المهمّة: %d وثيقة" % len(recs))
    return {"docs": len(recs), "result": str(result)}
