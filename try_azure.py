#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
try_azure.py — تجربة فعلية: قراءة document.pdf عبر Azure DI + مقارنتها بالمحرّك المحلي.

- يقرأ الإعداد من .env المحلي (لا أسرار في الكود ولا تُطبع).
- يشغّل المحرّك المحلي دائماً (Tesseract معزّز) → local_ocr_output.txt.
- إن كان Azure مُفعّلاً ومُهيّأ → يقرأ عبر Azure → azure_ocr_output.txt (وإلا ملاحظة سبب).
- يكتب مقارنة الجودة → ocr_comparison_report.txt، ويطبع تقريراً (بلا أي مفتاح).
- تراجع آمن: لا NotImplementedError؛ غياب Azure لا يُفشل التشغيل.
"""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
ENGINE = ROOT / "zaini_case_audit_output" / "scripts"
sys.path.insert(0, str(ENGINE))

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
AZ_OUT = ROOT / "azure_ocr_output.txt"
LOC_OUT = ROOT / "local_ocr_output.txt"
CMP = ROOT / "ocr_comparison_report.txt"


def main():
    if not DOC.exists():
        print("✗ لم يُعثر على document.pdf"); sys.exit(1)

    images = convert_from_path(str(DOC), dpi=RH.DPI)
    pages = len(images)

    # 1) المحرّك المحلي (دائماً)
    local_text = "\n".join(RH.best_page_text(im)[0] for im in images)
    LOC_OUT.write_text(local_text, encoding="utf-8")
    qm_local = RP.quality_metrics(local_text)

    # 2) Azure (إن فُعّل ومُهيّأ)
    print("ENGINE_MODE =", os.environ.get("ENGINE_MODE", "(غير مضبوط)"),
          "| AZURE_DI_ENABLED =", os.environ.get("AZURE_DI_ENABLED", "(غير مضبوط)"))
    print("Azure مُفعّل؟", azure_engine.enabled(), "| مُهيّأ (نقطة+مفتاح)؟", azure_engine.configured(),
          "| متاح (SDK+اتصال)؟", azure_engine.available())
    azure_text, qm_azure, azure_ran = None, None, False
    if azure_engine.available():
        print("→ القراءة عبر Azure Document Intelligence ...")
        azure_text = azure_engine.ocr_text(DOC)
        if azure_text and azure_text.strip():
            azure_ran = True
            qm_azure = RP.quality_metrics(azure_text)
            AZ_OUT.write_text(azure_text, encoding="utf-8")
        else:
            AZ_OUT.write_text("(Azure لم يُعِد نصاً — راجع الاتصال/الموديل.)", encoding="utf-8")
    else:
        why = ("غير مُفعّل (ENGINE_MODE=azure أو AZURE_DI_ENABLED=true)" if not azure_engine.enabled()
               else "غير مُهيّأ (AZURE_DI_ENDPOINT/AZURE_DI_KEY في .env)" if not azure_engine.configured()
               else "SDK غير مثبّت أو تعذّر الاتصال")
        AZ_OUT.write_text("(Azure لم يُشغّل — السبب: %s. استُخدم المحرّك المحلي.)" % why, encoding="utf-8")
        print("→ Azure لم يُشغّل:", why, "— التراجع للمحلي.")

    # 3) تقرير المقارنة
    lines = ["تقرير مقارنة OCR — Azure مقابل المحلي",
             "=" * 44,
             "الملف: document.pdf | الصفحات: %d" % pages,
             "",
             "المحرّك المحلي (Tesseract معزّز):",
             "  جودة: %.1f (%s) | نسبة عربية: %.3f | رموز غريبة: %d | لاتيني داخل عربي: %d | أحرف: %d" % (
                 qm_local["quality"], RP.grade(qm_local["quality"]), qm_local["ar_ratio"],
                 qm_local["bad_syms"], qm_local["latin_in_ar"], qm_local["chars"]),
             ""]
    if azure_ran:
        lines += ["Azure Document Intelligence:",
                  "  جودة: %.1f (%s) | نسبة عربية: %.3f | رموز غريبة: %d | لاتيني داخل عربي: %d | أحرف: %d" % (
                      qm_azure["quality"], RP.grade(qm_azure["quality"]), qm_azure["ar_ratio"],
                      qm_azure["bad_syms"], qm_azure["latin_in_ar"], qm_azure["chars"]),
                  "",
                  "الفرق في الجودة (Azure − المحلي): %+.1f" % (qm_azure["quality"] - qm_local["quality"]),
                  "التوصية: %s" % ("اعتماد Azure (أفضل)" if qm_azure["quality"] > qm_local["quality"] + 3
                                   else "متقاربان — أبقِ المحلي افتراضاً")]
    else:
        lines += ["Azure: لم يُشغّل (راجع azure_ocr_output.txt للسبب).",
                  "التوصية: اضبط .env بمفتاح صحيح وأعد التشغيل لإجراء المقارنة."]
    CMP.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print("\n================ تقرير try_azure ================")
    print("الصفحات:", pages)
    print("local_ocr_output.txt:", LOC_OUT.exists(), "(%d حرف)" % len(local_text))
    print("azure_ocr_output.txt:", AZ_OUT.exists())
    print("ocr_comparison_report.txt:", CMP.exists())
    print("جودة المحلي: %.1f (%s)" % (qm_local["quality"], RP.grade(qm_local["quality"])))
    if azure_ran:
        print("جودة Azure: %.1f (%s) | الفرق: %+.1f" % (
            qm_azure["quality"], RP.grade(qm_azure["quality"]), qm_azure["quality"] - qm_local["quality"]))
    else:
        print("Azure: لم يُشغّل (انظر السبب في azure_ocr_output.txt)")
    print("=================================================")


if __name__ == "__main__":
    main()
