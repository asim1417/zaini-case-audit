#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
try_azure.py — تجربة فعلية لقراءة document.pdf عبر Azure Document Intelligence.

- يقرأ الإعداد من .env المحلي (لا أسرار في الكود).
- إن كان Azure مُفعّلاً ومُهيّأ → يقرأ عبر Azure.
- وإلا (غير مُفعّل/غير مُهيّأ/SDK غير مثبّت أو فشل الاتصال) → يتراجع للمحرّك المحلي
  الحقيقي (Tesseract معزّز) — لا NotImplementedError.
- يكتب الناتج في azure_ocr_output.txt ويطبع تقريراً (المحرّك/الصفحات/تقييم العربية).
الملف المُجرَّب: document.pdf (غير سري). لا تُمرَّر أسرار في المحادثة.
"""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
ENGINE = ROOT / "zaini_case_audit_output" / "scripts"
sys.path.insert(0, str(ENGINE))

# تحميل .env إن وُجد (python-dotenv اختياري؛ وإلا قراءة يدوية بسيطة)
ENV = ROOT / ".env"
try:
    from dotenv import load_dotenv
    load_dotenv(ENV)
except Exception:
    if ENV.exists():
        for line in ENV.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())

import azure_engine
import reocr_pilot as RP
import reocr_hard as RH
from pdf2image import convert_from_path

DOC = ROOT / "document.pdf"
OUT = ROOT / "azure_ocr_output.txt"


def main():
    if not DOC.exists():
        print("✗ لم يُعثر على document.pdf في:", DOC)
        sys.exit(1)

    # عدد الصفحات (عبر تحويلها لصور — يلزم أيضاً للتراجع المحلي)
    images = convert_from_path(str(DOC), dpi=RH.DPI)
    pages = len(images)

    engine = None
    text = None
    print("ENGINE_MODE =", os.environ.get("ENGINE_MODE", "(غير مضبوط)"),
          "| AZURE_DI_ENABLED =", os.environ.get("AZURE_DI_ENABLED", "(غير مضبوط)"))
    print("Azure مُفعّل؟", azure_engine.enabled(), "| مُهيّأ (نقطة+مفتاح)؟", azure_engine.configured())

    if azure_engine.available():
        print("→ القراءة عبر Azure Document Intelligence ...")
        text = azure_engine.ocr_text(DOC)
        if text and text.strip():
            engine = "azure-document-intelligence"
        else:
            print("⚠ Azure لم يُعِد نصاً — تراجع للمحلي.")

    if text is None or not text.strip():
        why = ("غير مُفعّل (اضبط ENGINE_MODE=azure أو AZURE_DI_ENABLED=true)"
               if not azure_engine.enabled() else
               "غير مُهيّأ (AZURE_DI_ENDPOINT/AZURE_DI_KEY في .env)"
               if not azure_engine.configured() else
               "تعذّر الاتصال/SDK")
        print("→ التراجع للمحرّك المحلي (Tesseract معزّز). السبب: %s" % why)
        text = "\n".join(RH.best_page_text(im)[0] for im in images)
        engine = "local-fallback (tesseract-ara-enhanced)"

    OUT.write_text(text or "", encoding="utf-8")

    # تقييم أولي للنص العربي
    m = RP.quality_metrics(text or "")
    print("\n================ تقرير try_azure ================")
    print("المحرّك المستخدم      :", engine)
    print("عدد الصفحات          :", pages)
    print("أُنشئ azure_ocr_output.txt:", OUT.exists(), "(%d حرف)" % len(text or ""))
    print("نسبة الحروف العربية   :", m["ar_ratio"])
    print("درجة جودة النص (0-100):", m["quality"], "(%s)" % RP.grade(m["quality"]))
    print("رموز غريبة            :", m["bad_syms"], "| لاتيني داخل عربي:", m["latin_in_ar"])
    print("عيّنة (أول 200 حرف)   :", (text or "")[:200].replace("\n", " "))
    print("=================================================")


if __name__ == "__main__":
    main()
