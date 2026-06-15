#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
make_master_excel.py
ملف Excel رئيسي: صف واحد لكل مستند يضم الرابط والعنوان والتاريخ والقسم والنوع
وملخّصاً آلياً مهيكلاً والنص الكامل المقروء.
المخرج: outputs/excel/00_master_documents.xlsx  (+ نسخة CSV)
الاستخدام: python3 make_master_excel.py --staging <staging_dir>
"""
import argparse
import csv
import json
import re
from pathlib import Path

import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment
from openpyxl.utils import get_column_letter

import audit_zaini_case as AZ

OUT_XLSX = AZ.OUT_XLSX
OUT_CSV = AZ.OUT_CSV
OUT_JSON = AZ.OUT_JSON
TAG_S = AZ.TAG_SCRIPT
TAG_R = AZ.TAG_NEEDS_REVIEW

CELL_MAX = 32000  # حدّ خلية Excel ~32767
DATE_IN_TITLE = re.compile(r"(\d{1,2}[-/]\d{1,2}[-/]\d{3,4}|\d{3,4}[-/]\d{1,2}[-/]\d{1,2})")


def make_summary(f, text):
    e = f.get("entities", {})
    bits = [f"النوع: {f.get('doc_type','غير مصنف')}"]
    if e.get("parties"):
        bits.append("الأطراف: " + "، ".join(e["parties"]))
    if e.get("courts"):
        bits.append("المحاكم: " + "، ".join(e["courts"][:3]))
    if e.get("case_numbers"):
        bits.append("قضايا: " + "، ".join(e["case_numbers"]))
    if e.get("deed_numbers_known"):
        bits.append("صكوك: " + "، ".join(e["deed_numbers_known"]))
    if e.get("amounts"):
        # استبعد أرقام OCR الشاذة (أكبر من ~10 مليارات) من الملخّص
        clean_amts = [a for a in e["amounts"] if len(re.sub(r"[^\d]", "", a)) <= 10]
        if clean_amts:
            bits.append("مبالغ: " + "، ".join(clean_amts[:4]) + " ريال")
    if e.get("hijri_dates"):
        bits.append("تواريخ هجرية: " + "، ".join(e["hijri_dates"][:4]))
    # مقتطف افتتاحي نظيف
    snippet = re.sub(r"\s+", " ", text).strip()
    snippet = re.sub(r"^\[.*?\]\s*", "", snippet)  # احذف وسوم [أرشيف...]/[صفحة..]
    if snippet:
        bits.append("مقتطف: " + snippet[:300])
    return " | ".join(bits)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--staging", default=str(AZ.DEFAULT_STAGING))
    args = ap.parse_args()

    data = json.loads((OUT_JSON / "full_audit_data.json").read_text(encoding="utf-8"))
    files = data["files"]
    rdir = Path(args.staging) / "text_readable"
    tdir = Path(args.staging) / "text"
    fixed_ids = set()
    fx = rdir / "_fixed_ids.json"
    if fx.exists():
        fixed_ids = set(json.loads(fx.read_text(encoding="utf-8")))

    files.sort(key=lambda f: (f.get("parent_path", ""), f.get("title", "")))

    headers = ["#", "العنوان", "الرابط", "التاريخ", "القسم", "نوع المستند",
               "قابل للقراءة؟", "مصدر النص", "عدد الأحرف", "ملخّص آلي (يحتاج مراجعة)",
               "النص الكامل (مقروء)", "وسم"]

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "كل المستندات"
    ws.sheet_view.rightToLeft = True
    ws.append(headers)
    hfill = PatternFill("solid", fgColor="1F4E78")
    hfont = Font(bold=True, color="FFFFFF")
    for c in ws[1]:
        c.fill = hfill
        c.font = hfont
        c.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
    ws.freeze_panes = "A2"

    csv_rows = []
    n = 0
    for f in files:
        rp = rdir / f"{f['id']}.txt"
        p = rp if rp.exists() else (tdir / f"{f['id']}.txt")
        text = p.read_text(encoding="utf-8", errors="replace") if p.exists() else ""
        # التاريخ: من العنوان إن وُجد، وإلا تاريخ التعديل
        m = DATE_IN_TITLE.search(f.get("title", "") or "")
        date = m.group(1) if m else (f.get("modifiedTime", "") or "")[:10]
        src = "OCR مُصحَّح" if f["id"] in fixed_ids else ("منطقي" if text else "—")
        readable = "نعم" if f.get("readable") else "لا (يحتاج OCR/فك ضغط/غير متاح)"
        summary = make_summary(f, text)
        full = text if len(text) <= CELL_MAX else (text[:CELL_MAX] +
               f"\n\n[...النص مقطوع عند {CELL_MAX} حرفاً لحدود Excel — النص الكامل في "
               f"staging/text_readable/{f['id']}.txt]")
        n += 1
        row = [n, f.get("title", ""), f.get("viewUrl", ""), date,
               f.get("parent_path", ""), f.get("doc_type", ""), readable, src,
               f.get("text_chars", len(text)), summary, full, TAG_S]
        ws.append(row)
        # تنسيق صف
        r = ws.max_row
        ws.cell(r, 2).hyperlink = None
        link_cell = ws.cell(r, 3)
        if f.get("viewUrl"):
            link_cell.hyperlink = f["viewUrl"]
            link_cell.font = Font(color="0563C1", underline="single")
        for col in (2, 5, 10, 11):
            ws.cell(r, col).alignment = Alignment(wrap_text=True, vertical="top", horizontal="right")
        csv_rows.append([n, f.get("title", ""), f.get("viewUrl", ""), date,
                         f.get("parent_path", ""), f.get("doc_type", ""), readable, src,
                         f.get("text_chars", len(text)), summary,
                         text[:8000], TAG_S])  # CSV: نص مختصر لتفادي ضخامة الملف

    widths = [5, 42, 30, 14, 26, 16, 14, 12, 11, 60, 90, 22]
    for i, w in enumerate(widths, 1):
        ws.column_dimensions[get_column_letter(i)].width = w

    wb.save(str(OUT_XLSX / "00_master_documents.xlsx"))

    with open(OUT_CSV / "00_master_documents.csv", "w", encoding="utf-8-sig", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(headers[:10] + ["النص (أول 8000 حرف)", "وسم"])
        w.writerows(csv_rows)

    print(f"أُنشئ Excel الرئيسي: {n} مستنداً.")
    print(f" - {OUT_XLSX / '00_master_documents.xlsx'}")
    print(f" - {OUT_CSV / '00_master_documents.csv'} (نص مختصر)")


if __name__ == "__main__":
    main()
