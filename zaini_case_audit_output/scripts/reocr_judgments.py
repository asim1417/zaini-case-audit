#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
reocr_judgments.py
يعيد OCR لملفات PDF (أحكام/مذكرات رديئة المسح) من staging/reocr/*.pdf بدقة 300 DPI،
ويعتمد النسخة الأعلى «معقولية» (وفق قاموس عربي) فقط — فلا يجعل أي ملف أسوأ.
يكتب الناتج المعتمد إلى staging/text/<id>.txt (المصدر) ليلتقطه باقي خط المعالجة.
الاستخدام: python3 reocr_judgments.py <staging_dir>
"""
import sys
import re
from pathlib import Path

import improve_readability as IR  # القاموس ومنطق التطبيع

STAGING = Path(sys.argv[1] if len(sys.argv) > 1 else "staging")
REOCR = STAGING / "reocr"
TEXT = STAGING / "text"
RDIR = STAGING / "text_readable"


def density(text):
    """كثافة الكلمات المعجمية لكل 1000 حرف (مؤشر جودة القراءة)."""
    if not text:
        return 0.0
    return IR.line_score(text) / max(len(text), 1) * 1000.0


def ocr_pdf_hi(path, dpi=300, max_pages=40):
    import pytesseract
    from pdf2image import convert_from_path
    pages = convert_from_path(str(path), dpi=dpi)
    out = []
    for i, pg in enumerate(pages[:max_pages], 1):
        out.append(f"[صفحة {i}]")
        out.append(pytesseract.image_to_string(pg, lang="ara", config="--psm 6"))
    return "\n".join(out)


def main():
    if not REOCR.exists():
        print("لا يوجد مجلد reocr."); return
    adopted = kept = failed = 0
    rep = []
    for pdf in sorted(REOCR.glob("*.pdf")):
        fid = pdf.stem
        # النص الحالي (المقروء) للمقارنة
        cur = ""
        for cand in (RDIR / f"{fid}.txt", TEXT / f"{fid}.txt"):
            if cand.exists():
                cur = cand.read_text(encoding="utf-8", errors="replace"); break
        try:
            new = ocr_pdf_hi(pdf)
        except Exception as e:  # noqa
            failed += 1; rep.append(f"{fid} OCR-FAIL {e}"); continue
        dn, dc = density(new), density(cur)
        if dn >= dc * 1.02 and len(new.strip()) > 50:
            (TEXT / f"{fid}.txt").write_text(new, encoding="utf-8")
            adopted += 1
            rep.append(f"{fid} ADOPT new_density={dn:.1f} > old={dc:.1f}")
        else:
            kept += 1
            rep.append(f"{fid} KEEP old_density={dc:.1f} >= new={dn:.1f}")
    print(f"أُعيد OCR: اعتُمد {adopted} / أُبقي القديم {kept} / فشل {failed}")
    for line in rep:
        print("  ", line)


if __name__ == "__main__":
    main()
