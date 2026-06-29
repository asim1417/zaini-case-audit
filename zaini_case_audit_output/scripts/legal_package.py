#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
legal_package.py — بناء «حزمة وثائقية قانونية» منظمة قابلة للمراجعة من مصدر مستخرج آلياً.

ترقية فوق legal_clean: معرّفات ثابتة DOC-001، فهرس رئيسي قابل للنقر + فهارس فرعية
حسب النوع، بطاقة تعريف موسّعة لكل وثيقة، مقدمة منهجية، كشف الصفحات الفارغة والنصوص
المشوّهة، روابط داخلية (Word bookmarks/hyperlinks + HTML anchors + PDF bookmarks)،
وفهرس/بطاقات بصيغ Excel/CSV/JSON، وتقارير رقابية.

المبدأ: المحافظة على الأصل، لا اختلاق، كل غموض يُعلَّم. الصور/الأصل في Drive؛ التتبّع
على مستوى الصفحة دقيق حيث توجد علامات [صفحة N] وتقديري لغيرها (مُوضَّح في التقارير).

المخرجات في outputs/package/.
"""
import os, re, sys, json, csv, html, math, shutil, unicodedata, datetime, subprocess
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import legal_clean as LC

from docx import Document
from docx.shared import Pt, Cm, Mm, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_COLOR_INDEX
from docx.oxml.ns import qn
from docx.oxml import OxmlElement
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment

ROOT = Path(os.environ.get("CASE_ROOT") or Path(__file__).resolve().parent.parent)
IN = ROOT / "outputs" / "json" / "full_documents.jsonl"
OUTDIR = ROOT / "outputs" / "package"
UNCERTAIN = OUTDIR / "uncertain"
FONT = "Traditional Arabic"
TODAY = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
CHARS_PER_PAGE = 1800

CAT_MAP = {
    "حكم / صك": "الصكوك والأحكام",
    "عقد / اتفاقية": "العقود والاتفاقيات", "وكالة": "العقود والاتفاقيات",
    "مذكرة قضائية": "المذكرات القضائية واللوائح", "صحيفة دعوى": "المذكرات القضائية واللوائح",
    "شكوى": "الشكاوى والطلبات", "إخطار مطالبة": "الشكاوى والطلبات",
    "تقرير خبرة": "التقييمات المالية", "مستند مالي": "التقييمات المالية",
    "تقرير طبي": "التقارير الطبية",
    "مراسلة": "الخطابات والمراسلات", "محضر": "الخطابات والمراسلات",
}
CAT_ORDER = ["الصكوك والأحكام", "العقود والاتفاقيات", "المذكرات القضائية واللوائح",
             "الشكاوى والطلبات", "التقييمات المالية", "التقارير الطبية",
             "الخطابات والمراسلات", "التذاكر والإشعارات والمراجعات", "المرفقات الأخرى"]

DISTORT_RE = re.compile(r"[�?□�¿]{1,}|(.)\1{3,}")
BAD_SYMS = re.compile(r"[�□�]")


def category(doc_type):
    return CAT_MAP.get(doc_type, "المرفقات الأخرى")


def est_pages(text):
    n = len(re.findall(r"\[صفحة\s*\d+\]", text))
    if n:
        return n
    return max(1, math.ceil(len(text) / CHARS_PER_PAGE))


def split_pages(text):
    """يقسّم النص إلى صفحات عبر علامات [صفحة N]؛ يعيد قائمة (page_no, text)."""
    parts = re.split(r"\[\s*صفحة\s*(\d+)\s*\]", text)
    pages = []
    if len(parts) == 1:
        return [(1, text)]
    # parts: [pre, num, body, num, body, ...]
    i = 1
    pre = parts[0].strip()
    if pre:
        pages.append((0, pre))
    while i < len(parts) - 1:
        pages.append((int(parts[i]), parts[i + 1]))
        i += 2
    return pages


def detect_distortion(text):
    syms = len(BAD_SYMS.findall(text))
    reps = len(re.findall(r"(\S)\1{3,}", text))
    latin = len(re.findall(r"[A-Za-z]{3,}", text))
    frags = sum(1 for l in text.split("\n") if 0 < len(l.strip()) <= 2)
    total = len(text) or 1
    score = (syms * 3 + reps + frags) / max(1, total / 500)
    issues = []
    if syms:
        issues.append("رموز غريبة: %d" % syms)
    if reps:
        issues.append("تكرار حروف: %d" % reps)
    if frags > 5:
        issues.append("فُتات أسطر: %d" % frags)
    return {"syms": syms, "reps": reps, "latin": latin, "frags": frags,
            "score": round(score, 2), "issues": issues}


# ---------- روابط Word ----------
def add_bookmark(par, name, bid):
    s = OxmlElement("w:bookmarkStart"); s.set(qn("w:id"), str(bid)); s.set(qn("w:name"), name)
    e = OxmlElement("w:bookmarkEnd"); e.set(qn("w:id"), str(bid))
    par._p.insert(0, s); par._p.append(e)


def add_anchor_link(par, text, anchor, size=16):
    h = OxmlElement("w:hyperlink"); h.set(qn("w:anchor"), anchor)
    r = OxmlElement("w:r"); rPr = OxmlElement("w:rPr")
    rf = OxmlElement("w:rFonts"); rf.set(qn("w:cs"), FONT); rPr.append(rf)
    col = OxmlElement("w:color"); col.set(qn("w:val"), "0563C1"); rPr.append(col)
    u = OxmlElement("w:u"); u.set(qn("w:val"), "single"); rPr.append(u)
    rPr.append(OxmlElement("w:rtl"))
    sz = OxmlElement("w:szCs"); sz.set(qn("w:val"), str(size * 2)); rPr.append(sz)
    r.append(rPr)
    t = OxmlElement("w:t"); t.set(qn("xml:space"), "preserve"); t.text = text; r.append(t)
    h.append(r); par._p.append(h)


def _cell(cell, txt, bold=False, size=13):
    cell.text = ""
    p = cell.paragraphs[0]; p.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    p._p.get_or_add_pPr().append(OxmlElement("w:bidi"))
    if str(txt):
        r = p.add_run(LC.xml_safe(str(txt))); r.bold = bold; r.font.name = FONT; r.font.size = Pt(size)
        rpr = r._element.get_or_add_rPr(); rpr.get_or_add_rFonts().set(qn("w:cs"), FONT)
        rpr.append(OxmlElement("w:rtl"))
        szCs = OxmlElement("w:szCs"); szCs.set(qn("w:val"), str(size * 2)); rpr.append(szCs)


def is_financial(d):
    if d["doc_type"] in ("تقرير خبرة", "مستند مالي"):
        return True
    return bool(re.search(r"تقييم|مسحوب|مصروف|مصاريف|كشف\s*حساب|قروض|سلف|ميزاني|حقوق\s*الملكية|تقرير\s*مالي", d["title"]))


_MONEY_CTX = re.compile(r"مبلغ|قيم|ريال|مليون|مليار|[أا]لف|رصيد|حص[ةه]|تقييم|[إا]جمالي|محكوم|سداد|دفع|تعويض|دين")
_AR2EN = {ord(a): ord(e) for a, e in zip("٠١٢٣٤٥٦٧٨٩", "0123456789")}
_NUM = re.compile(r"(\d[\d.,٬٠-٩]{0,16})\s*(مليون|مليار|[أا]لف|ريال|ر\.?س|﷼)?")


def financial_figures(d):
    text = "\n".join(p[1] for p in d["paras"])
    figs, seen = [], set()
    for line in text.split("\n"):
        ctx_money = bool(_MONEY_CTX.search(line))
        for m in _NUM.finditer(line):
            num = m.group(1).strip(".,٬"); suf = m.group(2) or ""
            digits = re.sub(r"\D", "", num.translate(_AR2EN))
            if not digits:
                continue
            # تواريخ/أرقام قضايا ليست مبالغ
            if re.search(r"\d{1,2}[-/]\d{1,2}[-/]\d{2,4}", line) and not suf and not ctx_money:
                continue
            if os.environ.get("CASE_NUMBER") and digits == os.environ.get("CASE_NUMBER"):
                continue
            # مبلغ فعلي: إمّا بوحدة (مليون/ريال/ألف)، أو رقم كبير (≥6 خانات) في سياق مالي
            big = len(digits) >= 6
            if not (suf or (big and ctx_money)):
                continue
            if not suf and len(digits) >= 14:   # أرقام طويلة جداً = هويات/سجلات لا مبالغ
                continue
            key = digits + suf
            if key in seen:
                continue
            seen.add(key)
            ctx = re.sub(r"\s+", " ", line).strip()[:48]
            figs.append((ctx or "—", (num + ((" " + suf) if suf else "")).strip()))
    return figs[:50]


def add_financial_table(doc, d):
    figs = financial_figures(d)
    if not figs:
        return
    LC.add_par(doc, "أرقام ومبالغ مستخرجة آلياً من الوثيقة (للمراجعة — ليست جردًا محاسبيًا)",
               size=15, bold=True, color=RGBColor(0x1F, 0x4E, 0x79))
    t = doc.add_table(rows=1, cols=2); t.style = "Table Grid"
    t._tbl.tblPr.append(OxmlElement("w:bidiVisual"))
    _cell(t.rows[0].cells[0], "السياق", bold=True, size=13)
    _cell(t.rows[0].cells[1], "المبلغ/الرقم", bold=True, size=13)
    for ctx, val in figs:
        cells = t.add_row().cells
        _cell(cells[0], ctx, size=12); _cell(cells[1], val, size=12)
    doc.add_paragraph("")


def main():
    sample = None
    if "--sample" in sys.argv:
        sample = int(sys.argv[sys.argv.index("--sample") + 1])
    OUTDIR.mkdir(parents=True, exist_ok=True)
    UNCERTAIN.mkdir(parents=True, exist_ok=True)
    qc = LC.load_qc()
    recs = [json.loads(l) for l in open(IN, encoding="utf-8") if l.strip()]
    if sample:
        recs = recs[:sample]

    logs = {"hf": {}, "ocr_stats": {"ctrl": 0, "space": 0, "punct": 0}}
    docs = []
    blank_log, distort_log, uncertain_log = [], [], []
    cum_page = 1
    for i, rec in enumerate(recs, 1):
        did = "DOC-%03d" % i
        proc = LC.process_doc(rec, qc, logs)
        text = rec.get("full_text", "") or ""
        cat = category(proc["doc_type"])
        # صفحات + فراغات
        pages = split_pages(text)
        kept_pages, blanks = [], []
        for pno, ptext in pages:
            if len(re.sub(r"[\s\d٠-٩.,،\-_|]", "", ptext)) < 3:
                blanks.append(pno)
                blank_log.append({"doc": did, "title": proc["title"][:50], "page": pno,
                                  "reason": "مقطع صفحة بلا نص ذي معنى"})
            else:
                kept_pages.append((pno, ptext))
        npages = est_pages(text)
        if not text.strip():
            npages = 0
            uncertain_log.append({"doc": did, "title": proc["title"][:60],
                                  "reason": "بلا نص مستخرج (صورة/أرشيف) — يلزم الأصل"})
        # تشوّه
        dist = detect_distortion(text)
        if dist["issues"]:
            distort_log.append({"doc": did, "title": proc["title"][:50], **dist})
        page_start = cum_page
        cum_page += max(1, npages) if npages else 1
        page_end = cum_page - 1
        docs.append({**proc, "id": did, "cat": cat, "npages": npages,
                     "page_start": page_start, "page_end": page_end,
                     "blanks": blanks, "dist": dist,
                     "has_markers": bool(re.findall(r"\[صفحة\s*\d+\]", text))})

    dups = LC.detect_dups(recs)
    dup_titles = {}
    for a, b, r in dups:
        dup_titles.setdefault(a, []).append(b); dup_titles.setdefault(b, []).append(a)

    # ===== المخرجات =====
    write_html(docs, dups)
    build_docx(docs, dup_titles)
    part_paths = build_parts(docs, dup_titles)
    write_excel_index(docs)
    write_csv_index(docs)
    write_cards_json_excel(docs, dup_titles)
    write_reports(docs, dups, blank_log, distort_log, uncertain_log, logs)
    # نسخ سجل غير المؤكد كمجلد
    (UNCERTAIN / "README.txt").write_text(
        "مستندات/صفحات لم يمكن الجزم بمعالجتها — راجع الأصل في Google Drive.\n" +
        "\n".join("%s — %s (%s)" % (u["doc"], u["title"], u["reason"]) for u in uncertain_log),
        encoding="utf-8")
    LC.export_pdf(OUTDIR / "حزمة_الوثائق.docx", OUTDIR)
    for p in part_paths:
        LC.export_pdf(p, OUTDIR)
    print("الأجزاء المقسّمة:", len(part_paths))

    print("docs:", len(docs), "| فارغة:", len(blank_log), "| مشوّهة:", len(distort_log),
          "| غير مؤكد:", len(uncertain_log), "| تكرارات:", len(dups))


def card_fields(d, dup_titles):
    c = d["card"]
    return [
        ("رقم الوثيقة", d["id"]), ("نوع الوثيقة", d["doc_type"]),
        ("عنوان الوثيقة", d["title"]),
        ("التاريخ الهجري", c.get("التاريخ", "") if not re.search(r"20\d\d", c.get("التاريخ", "")) else ""),
        ("التاريخ الميلادي", c.get("التاريخ", "") if re.search(r"20\d\d", c.get("التاريخ", "")) else ""),
        ("الجهة المصدرة", c.get("الجهة المصدِرة") or c.get("الدائرة") or "غير متاح"),
        ("الأطراف/الأسماء", c.get("الأطراف", "غير متاح")),
        ("عدد الصفحات (تقديري)", str(d["npages"]) if d["npages"] else "صورة/بلا نص"),
        ("نطاق الصفحات في الملف", "%d–%d" % (d["page_start"], d["page_end"])),
        ("رابط المصدر الأصلي", d.get("viewUrl", "") or "غير متاح"),
        ("درجة وضوح الوثيقة", d["qc"].get("status", "غير متاح")),
        ("حالة OCR", "مستخرج آلياً" + ("؛ تشوّه: " + "، ".join(d["dist"]["issues"]) if d["dist"]["issues"] else "")),
        ("أختام/توقيعات", "يُراجع الأصل"),
        ("مرفقات تابعة", "نعم" if "مرفق" in d["title"] or "ومرفقات" in d["title"] else "غير محدّد"),
        ("نسخ مكرّرة", "نعم — راجع تقرير التكرارات" if d["title"] in dup_titles else "لا"),
        ("ملاحظات فنية", "؛ ".join(d["dist"]["issues"]) or "—"),
        ("ملاحظات وصفية", ("يحتاج مراجعة بشرية" if d["needs_review"] else "ضمن النطاق الواضح")),
    ]


# ---------- HTML (روابط داخلية موثوقة) ----------
def write_html(docs, dups):
    def e(s): return html.escape(str(s or ""))
    parts = ["<!DOCTYPE html><html lang='ar' dir='rtl'><head><meta charset='utf-8'>",
             "<title>الحزمة الوثائقية القانونية</title><style>",
             "body{font-family:'Traditional Arabic',Tahoma,serif;font-size:17px;line-height:1.8;margin:24px;color:#111}",
             "h1{font-size:24px}h2{font-size:20px;border-bottom:2px solid #1f4e79;color:#1f4e79}",
             "table{border-collapse:collapse;width:100%;font-size:14px}td,th{border:1px solid #bbb;padding:5px 8px;text-align:right}",
             "th{background:#eef}.card{background:#f8fafc;border:1px solid #cbd5e1;border-radius:8px;padding:10px 14px;margin:10px 0}",
             ".card td{border:none;padding:2px 6px}.doc{border-top:3px double #1f4e79;margin-top:30px;padding-top:8px}",
             ".note{color:#7c2d12}.back{font-size:13px}.txt{white-space:pre-wrap;word-break:break-word}",
             "a{color:#0563C1}.flag{background:#fef9c3}</style></head><body id='top'>"]
    # مقدمة منهجية
    parts.append("<h1>الحزمة الوثائقية القانونية</h1>")
    parts.append("<p class='note'>مخرج آلي تنظيمي يحتاج مراجعة بشرية — ليس رأياً قانونياً. وُلِّد %s.</p>" % e(TODAY))
    parts.append(methodology_html(len(docs)))
    # الفهرس الرئيسي
    parts.append("<h2 id='index'>الفهرس الرئيسي</h2>")
    parts.append("<table><tr><th>#</th><th>رقم الوثيقة</th><th>النوع</th><th>العنوان</th>"
                 "<th>التاريخ</th><th>الأطراف</th><th>صفحات</th><th>النطاق</th><th>الجودة</th></tr>")
    for n, d in enumerate(docs, 1):
        c = d["card"]
        parts.append("<tr><td>%d</td><td><a href='#%s'>%s</a></td><td>%s</td><td>%s</td>"
                     "<td>%s</td><td>%s</td><td>%s</td><td>%d–%d</td><td>%s</td></tr>" % (
                         n, d["id"], d["id"], e(d["doc_type"]), e(d["title"][:80]),
                         e(c.get("التاريخ", "")), e(c.get("الأطراف", "")[:40]),
                         d["npages"] or "—", d["page_start"], d["page_end"], e(d["qc"].get("status", ""))))
    parts.append("</table>")
    # فهارس فرعية
    parts.append("<h2>الفهارس الفرعية حسب النوع</h2>")
    for cat in CAT_ORDER:
        grp = [d for d in docs if d["cat"] == cat]
        if not grp:
            continue
        parts.append("<h3>%s (%d)</h3><ul>" % (e(cat), len(grp)))
        for d in grp:
            parts.append("<li><a href='#%s'>%s — %s</a></li>" % (d["id"], d["id"], e(d["title"][:90])))
        parts.append("</ul>")
    # الوثائق
    for d in docs:
        parts.append("<div class='doc' id='%s'><h2>%s — %s</h2>" % (d["id"], d["id"], e(d["title"])))
        parts.append("<div class='card'><b>بطاقة الوثيقة</b><table>")
        for k, v in card_fields(d, {}):
            vv = ("<a href='%s'>%s</a>" % (e(v), e(v))) if str(v).startswith("http") else e(v)
            parts.append("<tr><td><b>%s</b></td><td>%s</td></tr>" % (e(k), vv))
        parts.append("</table></div>")
        if is_financial(d):
            figs = financial_figures(d)
            if figs:
                parts.append("<h3>أرقام ومبالغ مستخرجة آلياً (للمراجعة)</h3><table><tr><th>السياق</th><th>المبلغ/الرقم</th></tr>")
                for ctx, val in figs:
                    parts.append("<tr><td>%s</td><td>%s</td></tr>" % (e(ctx), e(val)))
                parts.append("</table>")
            parts.append("<p class='note'>وثيقة مالية — التفريغ النصّي الكامل والجداول في «الملحق المالي» المستقل.</p>")
        else:
            body = "\n".join(p[1] if p[0] != "heading" else "\n【%s】" % p[1] for p in d["paras"])
            parts.append("<h3>تفريغ نص الوثيقة</h3><div class='txt'>%s</div>" % e(body))
        parts.append("<p class='back'><a href='#index'>↑ العودة إلى الفهرس</a></p></div>")
    parts.append("</body></html>")
    (OUTDIR / "حزمة_الوثائق.html").write_text("".join(parts), encoding="utf-8")


def methodology_html(n):
    items = [
        "هذا الملف تجميع وتنظيم وفهرسة لوثائق خام متعددة (%d وثيقة) مستخرجة آلياً (OCR)." % n,
        "أنواع الوثائق: صكوك وأحكام، عقود، مذكرات قضائية، شكاوى، تقييمات مالية، تقارير طبية، خطابات، مرفقات.",
        "استُخرجت النصوص آلياً ثم فُحصت: فصل الترويسات المكررة، ضبط المسافات، كشف التشوّه واختلاط الاتجاه.",
        "المستندات المصوّرة/الممسوحة: يُشار إليها وتُربط بأصلها؛ ولم يُختلق نص غير موجود.",
        "النصوص غير الواضحة مُيِّزت بوسوم مراجعة ولم تُصحَّح اجتهاداً.",
        "رُتِّبت الوثائق وأُعطيت معرّفات ثابتة DOC-001 فأعلى، ونطاقات صفحات تقديرية.",
        "الفهرس والبطاقات أدوات تنظيمية لا تغني عن مراجعة الأصل.",
        "الروابط الداخلية أُنشئت لتيسير التصفّح بين الفهرس والبطاقات والوثائق.",
    ]
    return "<h2>منهجية إعداد وتجهيز الحزمة الوثائقية</h2><ul>" + "".join("<li>%s</li>" % html.escape(x) for x in items) + "</ul>"


# ---------- DOCX ----------
_IDX_HEAD = ["#", "رقم الوثيقة", "العنوان", "النوع", "التاريخ", "الجودة"]
_IDX_W = [Cm(1.0), Cm(2.6), Cm(7.8), Cm(3.0), Cm(2.6), Cm(1.8)]
PART_GROUPS = [
    ("الصكوك والأحكام", ["الصكوك والأحكام"]),
    ("العقود والمرفقات", ["العقود والاتفاقيات", "المرفقات الأخرى"]),
    ("المذكرات القضائية واللوائح", ["المذكرات القضائية واللوائح", "التقارير الطبية"]),
    ("الشكاوى والطلبات", ["الشكاوى والطلبات"]),
    ("الخطابات والمحاضر والمراسلات", ["الخطابات والمراسلات"]),
]


# وضع مخفّف للمستند الواحد: بطاقات كأسطر بدل جداول + إيقاف التدقيق الخلفي (يمنع تجمّد Word).
LIGHT = os.environ.get("PACKAGE_LIGHT", "").strip().lower() in ("1", "true", "yes")


def _disable_proofing(doc):
    """يوقف عرض/حساب التدقيق الإملائي والنحوي الخلفي — يبطّئ Word بشدّة مع العربية الكثيرة."""
    s = doc.settings.element
    for tag in ("w:hideSpellingErrors", "w:hideGrammaticalErrors"):
        if s.find(qn(tag)) is None:
            s.append(OxmlElement(tag))


def _index_table(doc, docs):
    t = doc.add_table(rows=1, cols=len(_IDX_HEAD)); t.style = "Table Grid"; t.allow_autofit = False
    t._tbl.tblPr.append(OxmlElement("w:bidiVisual"))
    lay = OxmlElement("w:tblLayout"); lay.set(qn("w:type"), "fixed"); t._tbl.tblPr.append(lay)
    for c, htxt, w in zip(t.rows[0].cells, _IDX_HEAD, _IDX_W):
        _cell(c, htxt, bold=True, size=12); c.width = w
    for n, d in enumerate(docs, 1):
        cells = t.add_row().cells
        _cell(cells[0], str(n), size=11)
        _cell(cells[1], "", size=11); add_anchor_link(cells[1].paragraphs[0], d["id"], d["id"], size=11)
        _cell(cells[2], d["title"][:95], size=11)
        _cell(cells[3], d["doc_type"], size=11)
        _cell(cells[4], d["card"].get("التاريخ", ""), size=11)
        _cell(cells[5], d["qc"].get("status", ""), size=11)
        for c, w in zip(cells, _IDX_W):
            c.width = w


def _render_doc(doc, d, dup_titles, bid):
    doc.add_page_break()
    h = doc.add_paragraph(); h.style = doc.styles["Heading 1"]
    h.alignment = WD_ALIGN_PARAGRAPH.RIGHT; h._p.get_or_add_pPr().append(OxmlElement("w:bidi"))
    run = h.add_run("%s — %s" % (d["id"], d["title"])); run.font.name = FONT
    run._element.get_or_add_rPr().append(OxmlElement("w:rtl"))
    add_bookmark(h, d["id"], bid[0]); bid[0] += 1
    LC.add_par(doc, "بطاقة الوثيقة", size=20, bold=True, color=RGBColor(0x1F, 0x4E, 0x79))
    rows = [(k, v) for k, v in card_fields(d, dup_titles) if str(v).strip()]
    if LIGHT:
        # أسطر منسّقة بدل جدول — يخفّف تخطيط Word كثيراً (لا تجمّد) ويحفظ نفس الحقول.
        for k, v in rows:
            LC.add_par(doc, "%s: %s" % (k, str(v)[:400]), size=14)
    else:
        t = doc.add_table(rows=len(rows), cols=2); t.style = "Table Grid"
        t._tbl.tblPr.append(OxmlElement("w:bidiVisual"))
        for i, (k, v) in enumerate(rows):
            _cell(t.rows[i].cells[0], k, bold=True, size=15)
            _cell(t.rows[i].cells[1], str(v)[:400], size=15)
    doc.add_paragraph("")
    if is_financial(d):
        add_financial_table(doc, d)
        LC.add_par(doc, "وثيقة مالية — التفريغ النصّي الكامل والجداول في «الملحق المالي» المستقل.",
                   size=15, italic=True, color=RGBColor(0x7c, 0x2d, 0x12))
    else:
        LC.add_par(doc, "تفريغ نص الوثيقة", size=18, bold=True, color=RGBColor(0x1F, 0x4E, 0x79))
        for kind, tx, tags in d["paras"]:
            if kind == "heading":
                LC.add_par(doc, tx, size=20, bold=True, color=RGBColor(0x1F, 0x4E, 0x79))
            else:
                LC.add_par(doc, tx + (("  " + " ".join(tags)) if tags else ""), size=18, highlight=bool(tags))
    pb = doc.add_paragraph(); pb.alignment = WD_ALIGN_PARAGRAPH.CENTER
    pb._p.get_or_add_pPr().append(OxmlElement("w:bidi"))
    add_anchor_link(pb, "↑ العودة إلى الفهرس", "INDEX", size=13)


def _doc_shell(title_line):
    doc = Document(); LC.style_doc(doc); LC.set_section_rtl(doc.sections[0]); LC.add_footer_page(doc)
    p0 = LC.add_par(doc, title_line, size=24, bold=True, align="center")
    add_bookmark(p0, "top", 1)
    LC.add_par(doc, "مخرج آلي تنظيمي يحتاج مراجعة بشرية — ليس رأياً قانونياً · %s" % TODAY,
               size=14, italic=True, align="center", color=RGBColor(0x7c, 0x2d, 0x12))
    return doc


def build_parts(docs, dup_titles):
    """يقسّم الوثائق غير المالية إلى أجزاء حسب النوع؛ كل جزء ملف مستقل: فهرس جدولي + بطاقات + تفريغ."""
    paths = []
    for i, (name, cats) in enumerate(PART_GROUPS, 1):
        sub = [d for d in docs if d["cat"] in cats and not is_financial(d)]
        if not sub:
            continue
        doc = _doc_shell("حزمة الوثائق — الجزء %d: %s" % (i, name))
        LC.add_par(doc, "عدد وثائق هذا الجزء: %d" % len(sub), size=15, align="center")
        pidx = LC.add_par(doc, "فهرس وثائق هذا الجزء", size=22, bold=True, align="center")
        add_bookmark(pidx, "INDEX", 900 + i)
        _index_table(doc, sub)
        bid = [1000 * i]
        for d in sub:
            _render_doc(doc, d, dup_titles, bid)
        fn = OUTDIR / ("حزمة_الوثائق_جزء%d_%s.docx" % (i, name.replace(" ", "_")))
        doc.save(str(fn)); paths.append(fn)
    return paths


def build_docx(docs, dup_titles):
    doc = Document()
    LC.style_doc(doc)
    LC.set_section_rtl(doc.sections[0])
    LC.add_footer_page(doc)
    bid = [1]
    p0 = LC.add_par(doc, "الحزمة الوثائقية القانونية (النسخة الكاملة)", size=24, bold=True, align="center")
    add_bookmark(p0, "top", bid[0]); bid[0] += 1
    LC.add_par(doc, "مخرج آلي تنظيمي يحتاج مراجعة بشرية — ليس رأياً قانونياً · %s" % TODAY,
               size=14, italic=True, align="center", color=RGBColor(0x7c, 0x2d, 0x12))
    LC.add_par(doc, "منهجية إعداد وتجهيز الحزمة الوثائقية", size=22, bold=True)
    for line in ["تجميع وتنظيم وفهرسة لوثائق خام متعددة مستخرجة آلياً (OCR).",
                 "النصوص فُحصت: فصل الترويسات، ضبط المسافات، كشف التشوّه واختلاط الاتجاه؛ بلا اختلاق.",
                 "النصوص غير الواضحة مُيِّزت ولم تُصحَّح اجتهاداً؛ والمصوّرة تُربط بأصلها.",
                 "الوثائق المالية مفهرسة هنا ببطاقة وجدول مبالغ، وتفريغها الكامل في «الملحق المالي» المستقل.",
                 "هذه نسخة كاملة لكل الوثائق؛ وتتوفّر أيضاً أجزاء مقسّمة أخفّ للتصفّح."]:
        LC.add_par(doc, "• " + line, size=16)
    pidx = LC.add_par(doc, "الفهرس الرئيسي", size=22, bold=True, align="center")
    add_bookmark(pidx, "INDEX", bid[0]); bid[0] += 1
    _index_table(doc, docs)
    for d in docs:
        _render_doc(doc, d, dup_titles, bid)
    _disable_proofing(doc)
    doc.save(str(OUTDIR / "حزمة_الوثائق.docx"))


# ---------- Excel/CSV/JSON ----------
def write_excel_index(docs):
    wb = openpyxl.Workbook(); ws = wb.active; ws.title = "الفهرس الموحد"; ws.sheet_view.rightToLeft = True
    head = ["#", "رقم الوثيقة", "نوع الوثيقة", "العنوان", "التاريخ الهجري", "التاريخ الميلادي",
            "الجهة المصدرة", "الأطراف", "الموضوع المختصر", "عدد الصفحات", "نطاق الصفحات",
            "رابط داخلي", "رابط المصدر", "ملاحظات الجودة"]
    ws.append(head)
    for c in ws[1]:
        c.font = Font(bold=True); c.fill = PatternFill("solid", fgColor="DDEBF7")
    for n, d in enumerate(docs, 1):
        cd = d["card"]; greg = re.search(r"20\d\d", cd.get("التاريخ", ""))
        ws.append([n, d["id"], d["doc_type"], d["title"],
                   "" if greg else cd.get("التاريخ", ""), cd.get("التاريخ", "") if greg else "",
                   cd.get("الجهة المصدِرة") or cd.get("الدائرة") or "", cd.get("الأطراف", ""),
                   (d["title"][:60]), d["npages"] or "", "%d–%d" % (d["page_start"], d["page_end"]),
                   "حزمة_الوثائق.html#" + d["id"], d.get("viewUrl", ""), d["qc"].get("status", "")])
    wb.save(str(OUTDIR / "الفهرس_الموحد.xlsx"))


def write_csv_index(docs):
    with open(OUTDIR / "الفهرس_الموحد.csv", "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["#", "رقم الوثيقة", "نوع الوثيقة", "العنوان", "التاريخ", "الجهة", "الأطراف",
                    "عدد الصفحات", "نطاق الصفحات", "رابط داخلي", "رابط المصدر", "ملاحظات الجودة"])
        for n, d in enumerate(docs, 1):
            cd = d["card"]
            w.writerow([n, d["id"], d["doc_type"], d["title"], cd.get("التاريخ", ""),
                        cd.get("الجهة المصدِرة") or cd.get("الدائرة") or "", cd.get("الأطراف", ""),
                        d["npages"] or "", "%d–%d" % (d["page_start"], d["page_end"]),
                        "حزمة_الوثائق.html#" + d["id"], d.get("viewUrl", ""), d["qc"].get("status", "")])


def write_cards_json_excel(docs, dup_titles):
    cards = [{k: v for k, v in card_fields(d, dup_titles)} for d in docs]
    (OUTDIR / "بطاقات_الوثائق.json").write_text(json.dumps(cards, ensure_ascii=False, indent=1), encoding="utf-8")
    wb = openpyxl.Workbook(); ws = wb.active; ws.title = "بطاقات الوثائق"; ws.sheet_view.rightToLeft = True
    keys = [k for k, _ in card_fields(docs[0], dup_titles)] if docs else []
    ws.append(keys)
    for c in ws[1]:
        c.font = Font(bold=True); c.fill = PatternFill("solid", fgColor="E2EFDA")
    for d in docs:
        ws.append([v for _, v in card_fields(d, dup_titles)])
    wb.save(str(OUTDIR / "بطاقات_الوثائق.xlsx"))


# ---------- التقارير ----------
def write_reports(docs, dups, blank_log, distort_log, uncertain_log, logs):
    note = "> مخرج آلي تنظيمي يحتاج مراجعة بشرية — ليس رأياً قانونياً.\n\n"
    W = lambda name, t: (OUTDIR / name).write_text(t, encoding="utf-8")

    # النصوص المشوّهة
    r = ["# تقرير النصوص المشوّهة\n", note,
         "المعالجة محافظة: التشوّه مُكتشَف ومُعلَّم؛ لم يُصحَّح اجتهاداً ولم تُعَد OCR (الأصل في Drive والصور غير متاحة محلياً).",
         "", "| رقم الوثيقة | العنوان | الرموز الغريبة | تكرار حروف | فُتات | درجة | الإجراء |",
         "|---|---|---|---|---|---|---|"]
    for d in sorted(distort_log, key=lambda x: -x["score"]):
        r.append("| %s | %s | %d | %d | %d | %.2f | تعليم + يحتاج مراجعة بالأصل |" % (
            d["doc"], d["title"].replace("|", "/"), d["syms"], d["reps"], d["frags"], d["score"]))
    W("تقرير_النصوص_المشوهة.md", "\n".join(r) + "\n")

    # الصفحات الفارغة/المستبعدة
    r = ["# سجل الصفحات الفارغة والمستبعدة\n", note,
         "تعريف الفارغة هنا: مقطع صفحة (بين علامات [صفحة N]) بلا نص ذي معنى. التحقق البصري النهائي",
         "يحتاج الصورة الأصلية؛ لم تُحذف صفحة فيها أي أثر نصّي.", "",
         "| رقم الوثيقة | العنوان | الصفحة (خام) | سبب الاستبعاد |", "|---|---|---|---|"]
    for b in blank_log:
        r.append("| %s | %s | %s | %s |" % (b["doc"], b["title"].replace("|", "/"), b["page"], b["reason"]))
    if not blank_log:
        r.append("| — | — | — | لا صفحات فارغة مكتشفة في النصوص ذات العلامات |")
    W("سجل_الصفحات_الفارغة.md", "\n".join(r) + "\n")

    # التكرارات
    r = ["# تقرير التكرارات والنسخ المتعددة\n", note,
         "لم يُحذف أي مستند؛ النسخ قد تحمل فروقاً مؤثرة (ختم/توقيع/جودة).", "",
         "| الوثيقة (أ) | الوثيقة (ب) | نسبة التطابق | الإجراء |", "|---|---|---|---|"]
    for a, b, rr in dups:
        r.append("| %s | %s | %.0f%% | أُبقي الاثنان؛ يُشار للنسخة في البطاقة |" % (
            a[:40].replace("|", "/"), b[:40].replace("|", "/"), rr * 100))
    W("تقرير_التكرارات.md", "\n".join(r) + "\n")

    # حالات تحتاج مراجعة بشرية
    r = ["# تقرير حالات تحتاج مراجعة بشرية\n", note,
         "| رقم الوثيقة | العنوان | الأسباب |", "|---|---|---|"]
    for d in docs:
        reasons = []
        if d["dist"]["issues"]:
            reasons.append("تشوّه نص")
        if d["bidi_hits"]:
            reasons.append("اختلاط اتجاه")
        if d["tbl_hits"]:
            reasons.append("جدول مشتبه")
        if d["rev_residual"]:
            reasons.append("أسطر معكوسة")
        if not (d.get("npages")):
            reasons.append("بلا نص (صورة/أرشيف)")
        if d["qc"].get("status") not in ("سليم", ""):
            reasons.append("جودة منخفضة")
        if reasons:
            r.append("| %s | %s | %s |" % (d["id"], d["title"][:50].replace("|", "/"), "، ".join(reasons)))
    W("تقرير_حالات_تحتاج_مراجعة.md", "\n".join(r) + "\n")

    # تقرير الجودة النهائي
    raw_pages = sum(max(1, d["npages"]) for d in docs)
    need = sum(1 for d in docs if d["needs_review"])
    no_date = sum(1 for d in docs if not d["card"].get("التاريخ"))
    no_src = sum(1 for d in docs if not d.get("viewUrl"))
    links_ok = sum(1 for d in docs if d.get("viewUrl"))
    r = ["# تقرير فحص جودة الحزمة الوثائقية\n", note,
         "| المؤشّر | القيمة |", "|---|---|",
         "| عدد الوثائق قبل/بعد | %d / %d |" % (len(docs), len(docs)),
         "| الصفحات (تقديرية) | %d |" % raw_pages,
         "| صفحات فارغة مستبعدة | %d |" % len(blank_log),
         "| وثائق فيها تشوّه نصّي | %d |" % len(distort_log),
         "| وثائق تحتاج مراجعة بشرية | %d |" % need,
         "| وثائق بروابط مصدر مكتملة | %d |" % links_ok,
         "| وثائق ينقصها تاريخ | %d |" % no_date,
         "| وثائق ينقصها مصدر | %d |" % no_src,
         "| نسخ مكرّرة/شبه مكرّرة (أزواج) | %d |" % len(dups),
         "| وثائق بلا نص (صورة/أرشيف) | %d |" % len(uncertain_log),
         "", "## أهم المشاكل المتبقية",
         "- إعادة OCR ومقارنة الصورة تتطلّب الملفات الأصلية (في Google Drive).",
         "- ترتيب الأسطر المختلطة لا يُصحَّح آلياً دون إحداثيات OCR.",
         "- نطاقات الصفحات تقديرية (علامات صفحات صريحة في %d وثيقة فقط)." % sum(1 for d in docs if d.get("has_markers")),
         "", "## توصيات للمرحلة التالية",
         "- تزويد صور الصفحات/OCR بإحداثيات لإصلاح الترتيب وتأكيد الفراغات.",
         "- مراجعة الوثائق المُعلَّمة في «تقرير حالات تحتاج مراجعة» بالاستناد للأصل.", ""]
    W("تقرير_فحص_الجودة.md", "\n".join(r) + "\n")

    # document_index.json (تتبّع)
    idx = [{"id": d["id"], "order": i + 1, "type": d["doc_type"], "category": d["cat"],
            "title": d["title"], "pages_est": d["npages"], "page_range": [d["page_start"], d["page_end"]],
            "source": d.get("viewUrl", ""), "quality": d["qc"].get("status", ""),
            "needs_review": d["needs_review"], "anchor": d["id"]}
           for i, d in enumerate(docs)]
    (OUTDIR / "document_index.json").write_text(json.dumps(idx, ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
