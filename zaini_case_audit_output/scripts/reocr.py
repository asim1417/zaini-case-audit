#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
reocr.py
إعادة OCR للملفات ذات نص MCP الرديء (الأحكام/المحاضر المزدوجة) عبر tesseract مباشرةً
على صور صفحات الـPDF — متجاوزاً طبقة النص التالفة. يستبدل staging/text/<id>.txt.
الاستخدام: python3 reocr.py <staging_dir>
"""
import sys
from pathlib import Path

STAGING = Path(sys.argv[1] if len(sys.argv) > 1 else "staging")
REOCR = STAGING / "reocr"
TEXT = STAGING / "text"


def ocr_pdf(path, max_pages=60):
    import pytesseract
    from pdf2image import convert_from_path
    pages = convert_from_path(str(path), dpi=300)
    out = []
    for i, pg in enumerate(pages[:max_pages], 1):
        out.append(f"[صفحة {i}]")
        out.append(pytesseract.image_to_string(pg, lang="ara+eng"))
    return "\n".join(out)


def main():
    pdfs = sorted(REOCR.glob("*.pdf"))
    if not pdfs:
        print("لا توجد ملفات PDF في staging/reocr — لم يجرِ تنزيلها بعد.")
        return
    done = 0
    for p in pdfs:
        fid = p.stem
        try:
            txt = ocr_pdf(p)
            if len(txt.strip()) >= 30:
                (TEXT / f"{fid}.txt").write_text(txt, encoding="utf-8")
                done += 1
                print(f"  ✅ {fid}: {len(txt)} حرفاً")
            else:
                print(f"  ⚠️ {fid}: ناتج OCR ضئيل")
        except Exception as e:  # noqa
            print(f"  ❌ {fid}: {e}")
    print(f"أُعيد OCR لـ {done}/{len(pdfs)} ملفاً. شغّل run_all.sh لإعادة التوليد.")


if __name__ == "__main__":
    main()
