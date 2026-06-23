#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
financial_annex.py — الملحق المالي المستقل لوثائق التقييم والمصاريف والكشوفات.

يجمع الوثائق المالية (is_financial) ويعالجها بمنهجية مالية: جدول مبالغ لكل وثيقة +
تفريغ نصّي كامل + ورقة Excel بكل المبالغ. لا يخترع أرقاماً؛ كلها مستخرجة آلياً للمراجعة.
مخرجات: outputs/package/الملحق_المالي.docx + .xlsx
"""
import os, re, sys, json, datetime
from pathlib import Path

ROOT = Path(os.environ.get("CASE_ROOT") or Path(__file__).resolve().parent.parent)
sys.path.insert(0, str(ROOT / "scripts"))
import legal_clean as LC
import legal_package as LP
from docx import Document
from docx.shared import Pt, RGBColor
import openpyxl
from openpyxl.styles import Font, PatternFill

IN = ROOT / "outputs" / "json" / "full_documents.jsonl"
OUTDIR = ROOT / "outputs" / "package"
TODAY = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")


def main():
    qc = LC.load_qc()
    logs = {"hf": {}, "ocr_stats": {"ctrl": 0, "space": 0, "punct": 0}}
    recs = [json.loads(l) for l in open(IN, encoding="utf-8") if l.strip()]
    fin = []
    for i, r in enumerate(recs, 1):
        if LP.is_financial({"doc_type": r.get("doc_type", ""), "title": r.get("title", "")}):
            d = LC.process_doc(r, qc, logs)
            d["id"] = "DOC-%03d" % i
            d["figs"] = LP.financial_figures(d)
            fin.append(d)

    # ===== DOCX =====
    doc = Document(); LC.style_doc(doc); LC.set_section_rtl(doc.sections[0]); LC.add_footer_page(doc)
    LC.add_par(doc, "الملحق المالي — التقييمات والمصاريف والكشوفات", size=24, bold=True, align="center")
    LC.add_par(doc, "مخرج آلي يحتاج مراجعة بشرية — الأرقام مستخرجة آلياً (OCR) وقد تحوي أخطاءً · %s" % TODAY,
               size=14, italic=True, align="center", color=RGBColor(0x7c, 0x2d, 0x12))
    LC.add_par(doc, "عدد الوثائق المالية: %d" % len(fin), size=16, align="center")
    LC.add_par(doc, "منهجية: لكل وثيقة بطاقة موجزة ثم جدول بالمبالغ المستخرجة ثم التفريغ النصّي الكامل. "
                    "هذه أداة استرشاد لا تغني عن مراجعة الأصل والتدقيق المحاسبي.", size=15)
    # ملاحظة نزاع التقييم إن وُجد
    val = [d for d in fin if re.search(r"تقييم|تقدير\s*قيم|حقوق\s*الملكي", d["title"])]
    if val:
        LC.add_par(doc, "ملاحظة: من أبرز محاور النزاع تقييم شركة أحمد زيني التجارية (وردت قيم مختلفة "
                        "مثل 68 و79 مليون). الأرقام أدناه مستخرجة آلياً من وثائق التقييم للمراجعة.", size=15,
                   color=RGBColor(0x1F, 0x4E, 0x79))
    for d in fin:
        doc.add_page_break()
        h = doc.add_paragraph(); h.style = doc.styles["Heading 1"]
        from docx.enum.text import WD_ALIGN_PARAGRAPH
        from docx.oxml import OxmlElement
        from docx.oxml.ns import qn
        h.alignment = WD_ALIGN_PARAGRAPH.RIGHT; h._p.get_or_add_pPr().append(OxmlElement("w:bidi"))
        run = h.add_run("%s — %s" % (d["id"], d["title"])); run.font.name = LC.FONT
        run._element.get_or_add_rPr().append(OxmlElement("w:rtl"))
        c = d["card"]
        LC.add_par(doc, "النوع: %s · الجهة: %s · التاريخ: %s" % (
            d.get("doc_type", ""), c.get("الجهة المصدِرة") or c.get("الدائرة") or "—", c.get("التاريخ", "—")), size=15)
        LP.add_financial_table(doc, d)
        LC.add_par(doc, "التفريغ النصّي الكامل", size=16, bold=True, color=RGBColor(0x1F, 0x4E, 0x79))
        for kind, tx, tags in d["paras"]:
            LC.add_par(doc, tx, size=16, bold=(kind == "heading"))
    doc.save(str(OUTDIR / "الملحق_المالي.docx"))

    # ===== Excel =====
    wb = openpyxl.Workbook()
    ws = wb.active; ws.title = "كل المبالغ"; ws.sheet_view.rightToLeft = True
    ws.append(["رقم الوثيقة", "نوع الوثيقة", "العنوان", "السياق", "المبلغ/الرقم"])
    for cc in ws[1]:
        cc.font = Font(bold=True); cc.fill = PatternFill("solid", fgColor="DDEBF7")
    for d in fin:
        for ctx, val_ in d["figs"]:
            ws.append([d["id"], d.get("doc_type", ""), d["title"][:80], ctx, val_])
    ws2 = wb.create_sheet("الوثائق المالية"); ws2.sheet_view.rightToLeft = True
    ws2.append(["رقم الوثيقة", "النوع", "العنوان", "عدد المبالغ", "الرابط"])
    for cc in ws2[1]:
        cc.font = Font(bold=True); cc.fill = PatternFill("solid", fgColor="E2EFDA")
    for d in fin:
        ws2.append([d["id"], d.get("doc_type", ""), d["title"], len(d["figs"]), d.get("viewUrl", "")])
    wb.save(str(OUTDIR / "الملحق_المالي.xlsx"))

    LP.LC.export_pdf(OUTDIR / "الملحق_المالي.docx", OUTDIR)
    print("وثائق مالية:", len(fin), "| إجمالي المبالغ المستخرجة:", sum(len(d["figs"]) for d in fin))


if __name__ == "__main__":
    main()
