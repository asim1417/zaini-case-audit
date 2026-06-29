#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
reocr_pilot.py — تجربة أولية (عيّنة) لإعادة OCR انتقائية + معادلة جودة موثّقة.

يلتزم بالأمر الموجّه: لا يستبدل النص القديم إلا إذا تجاوزت جودة الجديد القديمَ بفارق
يتعدّى عتبة delta؛ يحفظ النسختين ودرجتيهما؛ يَسِم غير الواضح؛ لا يخترع نصاً.
المحرّك: Tesseract محلي (engine_mode=local). البنية تقبل محرّكاً سحابياً بمفتاح صريح.

المخرجات في outputs/reocr_pilot/:
  document_text_quality_report.csv (بالصفحة) ، review.html (صورة+قديم+جديد) ،
  modifications_log.md ، old_vs_new.csv ، ocr_text/*.txt (نسخ محفوظة).
"""
import os, re, sys, csv, json, base64, subprocess, unicodedata, datetime
from pathlib import Path
from io import BytesIO

from pdf2image import convert_from_path
from PIL import Image, ImageOps

ROOT = Path(os.environ.get("CASE_ROOT") or Path(__file__).resolve().parent.parent)
PILOT_IN = ROOT / "staging" / "reocr_pilot"
OUT = ROOT / "outputs" / "reocr_pilot"
TXT = OUT / "ocr_text"
IMG = OUT / "page_img"
DOCS = ROOT / "outputs" / "json" / "full_documents.jsonl"
DPI = 300
DELTA = 8.0           # عتبة فارق الجودة للاستبدال (موثّقة وقابلة للضبط)
LOW_QUALITY = 40      # دون هذا تُوسم الصفحة «تحتاج مراجعة»
TODAY = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")

# خريطة ملفات العيّنة → fileId الأصلي (لربط النص القديم)
SAMPLE = {}  # {"out.pdf": "<DRIVE_FILE_ID>"} عند الاستخدام


def clamp(x, a, b):
    return max(a, min(b, x))


def quality_metrics(text):
    """مؤشرات + درجة جودة موثّقة 0..100 ودرجة خطر 0..100."""
    t = unicodedata.normalize("NFKC", text or "")
    chars = len(t)
    letters = [c for c in t if c.isalpha()]
    ar = sum(1 for c in t if "؀" <= c <= "ۿ")
    nonar = len(letters) - ar
    ar_ratio = ar / max(1, len(letters))
    lines = t.split("\n")
    nonempty = [l for l in lines if l.strip()]
    short = sum(1 for l in nonempty if len(l.strip()) <= 2)
    numonly = sum(1 for l in nonempty if re.fullmatch(r"[\d٠-٩\s.\-_،|]+", l.strip() or "x"))
    bad = len(re.findall(r"[�□¿⸻]", t))
    latin_in_ar = len(re.findall(r"[؀-ۿ][A-Za-z]|[A-Za-z][؀-ۿ]", t))
    words = len(t.split())
    line_reg = 1 - short / max(1, len(nonempty))
    frag_ratio = short / max(1, len(nonempty))
    bad_ratio = bad / max(1, chars)
    # معادلة الجودة الموثّقة (أوزان قابلة للضبط):
    #   q = 100*(0.55*نسبة_عربية + 0.30*انتظام_الأسطر − 20*نسبة_الرموز − 0.15*نسبة_التقطيع)
    q = 100 * (0.55 * ar_ratio + 0.30 * line_reg - 20 * bad_ratio - 0.15 * frag_ratio)
    q = clamp(q, 0, 100)
    risk = clamp(100 - q + 25 * bad_ratio * 100 / max(1, 1), 0, 100)
    risk = clamp(100 - q, 0, 100)
    return {
        "chars": chars, "words": words, "ar_letters": ar, "nonar_letters": nonar,
        "ar_ratio": round(ar_ratio, 3), "bad_syms": bad, "bad_ratio": round(bad_ratio, 5),
        "short_lines": short, "num_only_lines": numonly, "latin_in_ar": latin_in_ar,
        "line_reg": round(line_reg, 3), "quality": round(q, 1), "risk": round(risk, 1),
    }


def grade(q):
    return ("ممتازة" if q >= 80 else "جيدة" if q >= 60 else "متوسطة" if q >= 40
            else "ضعيفة" if q >= 20 else "فشل/تحتاج مراجعة")


def preprocess(im):
    g = ImageOps.grayscale(im)
    g = ImageOps.autocontrast(g, cutoff=2)
    return g


def ocr(im):
    p = IMG / "_tmp.png"
    im.save(p)
    try:
        r = subprocess.run(["tesseract", str(p), "stdout", "-l", "ara", "--psm", "6"],
                           capture_output=True, text=True, timeout=120)
        return r.stdout
    except Exception as e:
        return ""


def old_text_for(file_id, recs):
    for r in recs:
        if file_id in (r.get("viewUrl", "") or ""):
            return r.get("title", ""), r.get("full_text", "") or ""
    return "", ""


def thumb_b64(im, w=360):
    t = im.copy(); t.thumbnail((w, w * 2))
    b = BytesIO(); t.save(b, format="JPEG", quality=60)
    return base64.b64encode(b.getvalue()).decode()


def main():
    OUT.mkdir(parents=True, exist_ok=True); TXT.mkdir(exist_ok=True); IMG.mkdir(exist_ok=True)
    recs = [json.loads(l) for l in open(DOCS, encoding="utf-8") if l.strip()]
    page_rows, doc_rows, html_blocks, modlog = [], [], [], []
    gpage = 0
    for fname, fid in SAMPLE.items():
        pdf = PILOT_IN / fname
        if not pdf.exists():
            continue
        title, old = old_text_for(fid, recs)
        old_q = quality_metrics(old)
        images = convert_from_path(str(pdf), dpi=DPI)
        new_full = []
        for pi, im in enumerate(images, 1):
            gpage += 1
            pim = preprocess(im)
            ntext = ocr(pim)
            new_full.append(ntext)
            m = quality_metrics(ntext)
            (TXT / ("%s_p%02d.txt" % (fname, pi))).write_text(ntext, encoding="utf-8")
            action = ("مقبول" if m["quality"] >= 60 else
                      "يحتاج مراجعة بشرية" if m["quality"] < LOW_QUALITY else "يحتاج مقارنة بالصورة")
            page_rows.append({
                "رقم الوثيقة": fid[:8], "العنوان": title[:40], "ملف العيّنة": fname,
                "صفحة عامة": gpage, "صفحة الوثيقة": pi,
                "كلمات": m["words"], "حروف عربية": m["ar_letters"], "حروف غير عربية": m["nonar_letters"],
                "رموز غريبة": m["bad_syms"], "نسبة التشوه%": round(m["bad_ratio"] * 100, 3),
                "أسطر قصيرة": m["short_lines"], "أسطر أرقام": m["num_only_lines"],
                "لاتيني داخل عربي": m["latin_in_ar"], "نسبة عربية": m["ar_ratio"],
                "انتظام الأسطر": m["line_reg"], "درجة الجودة": m["quality"], "التقدير": grade(m["quality"]),
                "درجة الخطر": m["risk"], "الإجراء المقترح": action,
                "مقتطف": re.sub(r"\s+", " ", ntext)[:80],
            })
            html_blocks.append((fid, title, pi, thumb_b64(im),
                                old[:1500] if pi == 1 else "(النص القديم على مستوى الوثيقة)", ntext[:1500],
                                m))
        new_q = quality_metrics("\n".join(new_full))
        replace = (new_q["quality"] - old_q["quality"]) > DELTA
        doc_rows.append({"fid": fid, "title": title, "pages": len(images),
                         "old_q": old_q["quality"], "new_q": new_q["quality"],
                         "delta": round(new_q["quality"] - old_q["quality"], 1),
                         "decision": "استبدال (الجديد أفضل بوضوح)" if replace else "إبقاء القديم (الفارق دون العتبة)"})
        modlog.append("- %s «%s»: جودة قديم=%.1f، جديد=%.1f، فارق=%.1f، delta=%.0f → %s (النسختان محفوظتان)" % (
            fid[:8], title[:40], old_q["quality"], new_q["quality"], new_q["quality"] - old_q["quality"],
            DELTA, "استبدال" if replace else "إبقاء"))

    # تقرير الجودة بالصفحة (CSV BOM)
    with open(OUT / "document_text_quality_report.csv", "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(page_rows[0].keys()))
        w.writeheader(); w.writerows(page_rows)
    # قديم مقابل جديد
    with open(OUT / "old_vs_new.csv", "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["fid", "title", "pages", "old_q", "new_q", "delta", "decision"])
        w.writeheader(); w.writerows(doc_rows)
    # سجل التعديلات
    (OUT / "modifications_log.md").write_text(
        "# سجل التعديلات — تجربة إعادة OCR (عيّنة)\n\n> مخرج آلي يحتاج مراجعة بشرية.\n\n"
        "المحرّك: Tesseract (ara) محلي · DPI=%d · عتبة الاستبدال delta=%.0f · %s\n\n"
        "قاعدة الاستبدال: لا يُستبدل القديم إلا إذا (جودة الجديد − جودة القديم) > delta؛ "
        "النسختان محفوظتان مع درجتيهما.\n\n## القرارات\n%s\n" % (DPI, DELTA, TODAY, "\n".join(modlog)),
        encoding="utf-8")
    # نسخة المراجعة HTML (صورة + قديم + جديد)
    write_review_html(html_blocks)
    print("صفحات العيّنة:", len(page_rows), "| وثائق:", len(doc_rows))
    for d in doc_rows:
        print("  %s | قديم=%.1f جديد=%.1f Δ=%.1f → %s" % (d["title"][:34], d["old_q"], d["new_q"], d["delta"], d["decision"]))


def write_review_html(blocks):
    import html as H
    p = ["<!DOCTYPE html><html lang='ar' dir='rtl'><head><meta charset='utf-8'><title>نسخة المراجعة — عيّنة OCR</title>",
         "<style>body{font-family:'Traditional Arabic',Tahoma,serif;margin:18px;font-size:16px}",
         ".pg{display:flex;gap:14px;border:1px solid #ccc;border-radius:10px;padding:12px;margin:14px 0}",
         ".pg img{max-width:340px;border:1px solid #999}.col{flex:1;min-width:0}",
         "h3{color:#1f4e79}.old{background:#fff7ed}.new{background:#f0fdf4}",
         "pre{white-space:pre-wrap;word-break:break-word;font-family:inherit;font-size:14px;max-height:420px;overflow:auto;border:1px solid #ddd;padding:8px}",
         ".risk{font-weight:bold}.bad{color:#b91c1c}</style></head><body>",
         "<h1>نسخة المراجعة — عيّنة إعادة OCR</h1>",
         "<p style='color:#7c2d12'>مخرج آلي يحتاج مراجعة بشرية — الصورة الأصلية هي المرجع عند التعارض. %s</p>" % TODAY]
    for fid, title, pi, b64, old, new, m in blocks:
        p.append("<div class='pg'><div><img src='data:image/jpeg;base64,%s'></div>" % b64)
        p.append("<div class='col'><h3>%s — صفحة %d</h3><p class='risk %s'>الجودة: %.1f (%s) · الخطر: %.1f</p>" % (
            H.escape(title[:50]), pi, "bad" if m["quality"] < 40 else "", m["quality"], grade(m["quality"]), m["risk"]))
        p.append("<b>النص الجديد (OCR)</b><pre class='new'>%s</pre>" % H.escape(new))
        p.append("<b>النص القديم</b><pre class='old'>%s</pre></div></div>" % H.escape(old))
    p.append("</body></html>")
    (OUT / "review.html").write_text("".join(p), encoding="utf-8")


if __name__ == "__main__":
    main()
