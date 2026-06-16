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
import make_word as MW  # لإعادة استخدام دوال Word (RTL/عناوين)

OUT_XLSX = AZ.OUT_XLSX
OUT_CSV = AZ.OUT_CSV
OUT_JSON = AZ.OUT_JSON
OUT_WORD = AZ.OUTPUT_ROOT / "outputs" / "word"
DOCS_DIR = OUT_WORD / "documents"
DOCS_DIR.mkdir(parents=True, exist_ok=True)
TAG_S = AZ.TAG_SCRIPT
TAG_R = AZ.TAG_NEEDS_REVIEW

CELL_MAX = 32000  # حدّ خلية Excel ~32767
DATE_IN_TITLE = re.compile(r"(\d{1,2}[-/]\d{1,2}[-/]\d{3,4}|\d{3,4}[-/]\d{1,2}[-/]\d{1,2})")


def safe_name(s):
    s = re.sub(r"[\\/:*?\"<>|\n\r\t]", "_", s or "")
    s = re.sub(r"\s+", " ", s).strip()
    # احذف الامتداد الأصلي إن وُجد لتفادي الامتداد المزدوج (مثل .pdf.docx)
    s = re.sub(r"\.(pdf|docx?|xlsx?|jpe?g|png|rar|zip|txt)$", "", s, flags=re.I).strip()
    return s[:80]


def write_doc_word(n, f, text, fixed):
    """ملف Word مستقل بالنص الكامل لمستند واحد (لا قصّ)."""
    from docx import Document
    from docx.shared import RGBColor
    doc = Document()
    MW.style_doc(doc)
    MW.add_heading_rtl(doc, f.get("title", "")[:150], level=1)
    meta = (f"الرقم: {n} | النوع: {f.get('doc_type','')} | التاريخ: "
            f"{DATE_IN_TITLE.search(f.get('title','') or '').group(1) if DATE_IN_TITLE.search(f.get('title','') or '') else (f.get('modifiedTime','') or '')[:10]} | "
            f"القسم: {f.get('parent_path','')}")
    MW.add_para_rtl(doc, meta, italic=True, color=RGBColor(0x55, 0x55, 0x55))
    MW.add_para_rtl(doc, "الرابط: " + (f.get("viewUrl", "") or ""), italic=True,
                    color=RGBColor(0x05, 0x63, 0xC1))
    MW.add_para_rtl(doc, f"{TAG_S}  {TAG_R}", italic=True)
    if f["id"] in fixed:
        MW.add_para_rtl(doc, "[نص ممسوح OCR صُحِّح ترتيبه آلياً — قد يحتوي أخطاء طفيفة]",
                        italic=True, color=RGBColor(0xC0, 0x00, 0x00))
    doc.add_paragraph("")
    # للأحكام/الصكوك/المحاضر/المذكرات: قسّم النص إلى أقسام واضحة (ترويسة/أطراف/متن)
    body = text
    if f.get("doc_type") in ("حكم / صك", "محضر", "مذكرة قضائية", "صحيفة دعوى",
                             "شكوى", "إخطار مطالبة", "مراسلة"):
        try:
            import format_minutes as FM
            body = FM.structure_text(text)
        except Exception:  # noqa
            body = text
    for chunk in re.split(r"\n{2,}", body):
        chunk = chunk.strip()
        if not chunk:
            continue
        # اجعل عناوين الأقسام بارزة (تبدأ بـ === أو خط فاصل)
        if chunk.startswith("=== ") or chunk.startswith("─"):
            MW.add_heading_rtl(doc, chunk.strip("= ─"), level=2)
            continue
        for i in range(0, len(chunk), 6000):
            MW.add_para_rtl(doc, chunk[i:i + 6000])
    fname = f"{n:03d}_{safe_name(f.get('title',''))}.docx"
    doc.save(str(DOCS_DIR / fname))
    return f"word/documents/{fname}"


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


def availability(f):
    """حالة إتاحة الرابط/الملف على Drive."""
    if f.get("readable"):
        return "متاح ✓"
    t = f.get("title", "") or ""
    if re.search(r"\(zip\)|\.zip|\bzip\b|\(rar\)|\.rar|\brar\b", t, re.I):
        return "أرشيف كبير — افتحه يدوياً من Drive (لم يُستخرج نصه آلياً)"
    if re.search(r"صورة|\.jpg|\.jpeg|\.png", t, re.I):
        return "صورة — افتحها من Drive"
    return "⚠️ رابط محذوف — الملف غير موجود في Drive"


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

    headers = ["#", "العنوان", "إتاحة الرابط", "رابط Drive", "ملف Word للنص الكامل",
               "التاريخ", "القسم", "نوع المستند", "قابل للقراءة؟", "مصدر النص",
               "عدد الأحرف", "ملخّص آلي (يحتاج مراجعة)", "وسم"]

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
        n += 1
        # ملف Word مستقل بالنص الكامل (لا قصّ) — يُنشأ فقط للملفات المقروءة
        word_rel = write_doc_word(n, f, text, fixed_ids) if text else ""
        avail = availability(f)
        row = [n, f.get("title", ""), avail, f.get("viewUrl", ""), word_rel, date,
               f.get("parent_path", ""), f.get("doc_type", ""), readable, src,
               f.get("text_chars", len(text)), summary, TAG_S]
        ws.append(row)
        # تنسيق صف
        r = ws.max_row
        # عمود الإتاحة (3): لوّن المحذوف بالأحمر، الأرشيف بالبرتقالي
        acell = ws.cell(r, 3)
        if avail.startswith("⚠️"):
            acell.font = Font(color="C00000", bold=True)
        elif "أرشيف" in avail or "صورة" in avail:
            acell.font = Font(color="BF8F00")
        link_cell = ws.cell(r, 4)
        if f.get("viewUrl") and not avail.startswith("⚠️"):
            link_cell.value = "🔗 فتح في Drive"
            link_cell.hyperlink = f["viewUrl"]
            link_cell.font = Font(color="0563C1", underline="single")
        elif avail.startswith("⚠️"):
            link_cell.value = "(رابط محذوف — لا تفتحه)"
            link_cell.font = Font(color="C00000")
        wcell = ws.cell(r, 5)
        if word_rel:
            wcell.hyperlink = "../" + word_rel  # رابط نسبي من مجلد excel إلى word
            wcell.value = "📄 فتح المستند (Word)"
            wcell.font = Font(color="0563C1", underline="single", bold=True)
        for col in (2, 3, 7, 12):
            ws.cell(r, col).alignment = Alignment(wrap_text=True, vertical="top", horizontal="right")
        csv_rows.append([n, f.get("title", ""), avail, f.get("viewUrl", ""), word_rel, date,
                         f.get("parent_path", ""), f.get("doc_type", ""), readable, src,
                         f.get("text_chars", len(text)), summary, TAG_S])

    widths = [5, 44, 26, 18, 22, 13, 24, 15, 22, 12, 10, 65, 18]
    for i, w in enumerate(widths, 1):
        ws.column_dimensions[get_column_letter(i)].width = w

    wb.save(str(OUT_XLSX / "00_master_documents.xlsx"))

    with open(OUT_CSV / "00_master_documents.csv", "w", encoding="utf-8-sig", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(headers)
        w.writerows(csv_rows)

    nword = len(list(DOCS_DIR.glob("*.docx")))
    print(f"أُنشئ Excel الرئيسي: {n} مستنداً.")
    print(f"ملفات Word مستقلة بالنص الكامل: {nword} في {DOCS_DIR}")
    print(f" - {OUT_XLSX / '00_master_documents.xlsx'}")
    print(f" - {OUT_CSV / '00_master_documents.csv'} (نص مختصر)")


if __name__ == "__main__":
    main()
