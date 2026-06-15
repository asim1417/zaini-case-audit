#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
qc_readability.py
فحص جودة آلي لكل ملفات النص المقروء (text_readable):
  - يقيس بقايا الأسطر المعكوسة (لم تُصحَّح) لكل ملف.
  - يقيس نسبة الكلمات العربية المعقولة (مؤشر تشويش OCR).
  - يصنّف كل ملف: سليم / يحتاج مراجعة (أسطر معكوسة) / تشويش OCR مرتفع.
يُخرج: outputs/csv/14_readability_qc.csv + ملخّص على الشاشة.
الاستخدام: python3 qc_readability.py <staging_dir>
"""
import sys
import re
import csv
import json
from pathlib import Path

import audit_zaini_case as AZ

STAGING = Path(sys.argv[1] if len(sys.argv) > 1 else "staging")
RDIR = STAGING / "text_readable"
OUT_CSV = AZ.OUT_JSON.parent / "csv"

import improve_readability as IR  # نفس القاموس ومنطق العكس لضمان الاتساق
# قاموس بسيط لكلمات عربية شائعة لقياس المعقولية
COMMON = set("""في من على إلى عن مع هذا هذه التي الذي قد كما حيث أن إن ما لا
المدعي المدعى عليه الحكم الدعوى المحكمة الدائرة العقد البيع الشركة الحصص المبلغ
ريال تاريخ رقم صك نظام المادة الاستئناف التجارية زيني احمد اسامة عدنان عاتقة
الوالد المورث الثمن السداد التقرير الخبير القيمة الشيخ ضد بشأن وقد وفي ولا وهو
بسم الله الرحمن الرحيم السلام عليكم ورحمة وبركاته بعد الموضوع الطرف الاسم""".split())

AR = re.compile(r"[؀-ۿ]")


def line_still_reversed(line):
    # السطر «معكوس متبقٍ» إذا كان عكسه أعلى معقولية وفق القاموس
    import unicodedata
    norm = unicodedata.normalize("NFKC", line)
    return IR.line_score(IR.reverse_line(norm)) > IR.line_score(norm)


def arabic_word_ratio(text):
    toks = [t for t in re.split(r"\s+", text) if AR.search(t)]
    if not toks:
        return 0.0, 0
    good = sum(1 for t in toks if t.strip("().،:؛-") in COMMON or
               (len(t) >= 3 and len(AR.findall(t)) / max(len(t), 1) > 0.7))
    return good / len(toks), len(toks)


def main():
    data = json.loads((AZ.OUT_JSON / "full_audit_data.json").read_text(encoding="utf-8"))
    by_id = {f["id"]: f for f in data["files"]}
    rows = []
    clean = rev_flag = noise_flag = 0
    for p in sorted(RDIR.glob("*.txt")):
        if p.name.startswith("_"):
            continue
        fid = p.stem
        text = p.read_text(encoding="utf-8", errors="replace")
        lines = [l for l in text.split("\n") if l.strip()]
        rev_lines = sum(1 for l in lines if line_still_reversed(l))
        ratio, ntok = arabic_word_ratio(text)
        status = "سليم"
        if rev_lines > 0:
            status = "أسطر معكوسة متبقية"
            rev_flag += 1
        elif ntok > 40 and ratio < 0.35:
            status = "تشويش OCR مرتفع"
            noise_flag += 1
        else:
            clean += 1
        f = by_id.get(fid, {})
        rows.append([f.get("title", fid)[:70], status, len(lines), rev_lines,
                     f"{ratio:.2f}", ntok, f.get("doc_type", ""), f.get("parent_path", "")])
    rows.sort(key=lambda r: (r[1] == "سليم", -int(r[3]), float(r[4])))
    with open(OUT_CSV / "14_readability_qc.csv", "w", encoding="utf-8-sig", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["الملف", "الحالة", "أسطر", "أسطر معكوسة متبقية",
                    "نسبة عربية معقولة", "عدد كلمات", "النوع", "القسم"])
        w.writerows(rows)
    total = clean + rev_flag + noise_flag
    print(f"فُحص {total} ملفاً مقروءاً:")
    print(f"  ✅ سليم: {clean}")
    print(f"  🔁 فيه أسطر معكوسة متبقية: {rev_flag}")
    print(f"  ⚠️ تشويش OCR مرتفع: {noise_flag}")
    print("\nأكثر 12 ملفاً يحتاج انتباهاً:")
    for r in rows:
        if r[1] != "سليم":
            print(f"  [{r[1]}] معكوسة={r[3]} نسبة={r[4]} | {r[0]}")
    print(f"\nالتقرير: {OUT_CSV / '14_readability_qc.csv'}")


if __name__ == "__main__":
    main()
