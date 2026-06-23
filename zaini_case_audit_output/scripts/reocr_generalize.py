#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
reocr_generalize.py — تعميم إعادة OCR الانتقائية على الوثائق المعيبة القابلة للتنزيل.

يلتزم بالأمر: لا استبدال إلا إذا (جودة الجديد − جودة القديم) > delta؛ النسختان محفوظتان؛
نسخة احتياطية من full_documents.jsonl قبل أي تعديل؛ سجل تعديلات وتقرير مقارنة كامل.
لا يخترع نصاً. المحرّك: Tesseract محلي (engine_mode=local).

المدخلات: staging/reocr_batch/<fileId>.pdf (نزّلها وكيل التنزيل) + _candidates.json.
المخرجات: full_documents.jsonl محدّث (+ نسخة احتياطية) و outputs/reocr_update/*.
"""
import os, re, sys, csv, json, shutil, datetime
from pathlib import Path

from pdf2image import convert_from_path
from PIL import Image

ROOT = Path(os.environ.get("CASE_ROOT") or Path(__file__).resolve().parent.parent)
sys.path.insert(0, str(ROOT / "scripts"))
import reocr_pilot as RP

BATCH = ROOT / "staging" / "reocr_batch"
JSONL = ROOT / "outputs" / "json" / "full_documents.jsonl"
OUT = ROOT / "outputs" / "reocr_update"
TXT = OUT / "ocr_text"
BACKUP = OUT / "_backup"
CAND = ROOT / "outputs" / "reocr_pilot" / "_candidates.json"
DELTA = 8.0
TODAY = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")


def main():
    OUT.mkdir(parents=True, exist_ok=True); TXT.mkdir(exist_ok=True); BACKUP.mkdir(exist_ok=True)
    recs = [json.loads(l) for l in open(JSONL, encoding="utf-8") if l.strip()]
    by_fid = {}
    for r in recs:
        m = re.search(r"/d/([A-Za-z0-9_-]+)", r.get("viewUrl", "") or "")
        if m:
            by_fid[m.group(1)] = r
    cands = json.load(open(CAND, encoding="utf-8"))
    # نسخة احتياطية من المصدر قبل أي تعديل
    shutil.copy2(JSONL, BACKUP / ("full_documents.%s.jsonl" % datetime.datetime.now().strftime("%Y%m%d_%H%M%S")))

    rows, comp, modlog = [], [], []
    replaced = 0
    for c in cands:
        fid = c["fid"]; pdf = BATCH / (fid + ".pdf")
        rec = by_fid.get(fid)
        if not pdf.exists() or rec is None:
            comp.append({"fid": fid[:8], "title": c["title"][:40], "status": "تعذّر (لم يُنزّل/غير موجود)",
                         "old_q": "", "new_q": "", "delta": "", "decision": "بقي القديم — يحتاج الأصل"})
            continue
        old = rec.get("full_text", "") or ""
        old_q = RP.quality_metrics(old)["quality"]
        try:
            sig = open(pdf, "rb").read(4)
            if sig[:4] == b"%PDF":
                images = convert_from_path(str(pdf), dpi=RP.DPI)
            else:  # صورة (JPEG/PNG) محفوظة بامتداد pdf
                images = [Image.open(pdf).convert("RGB")]
        except Exception as e:
            comp.append({"fid": fid[:8], "title": c["title"][:40], "status": "فشل التحويل لصور",
                         "old_q": round(old_q, 1), "new_q": "", "delta": "", "decision": "بقي القديم"})
            continue
        new_pages = []
        for pi, im in enumerate(images, 1):
            ntext = RP.ocr(RP.preprocess(im))
            new_pages.append(ntext)
            m = RP.quality_metrics(ntext)
            rows.append({"fid": fid[:8], "title": c["title"][:40], "صفحة": pi,
                         "كلمات": m["words"], "نسبة عربية": m["ar_ratio"], "رموز": m["bad_syms"],
                         "جودة": m["quality"], "تقدير": RP.grade(m["quality"]), "خطر": m["risk"]})
        new = "\n".join(new_pages)
        new_q = RP.quality_metrics(new)["quality"]
        (TXT / (fid + ".txt")).write_text(new, encoding="utf-8")
        do = (new_q - old_q) > DELTA
        if do:
            # احفظ القديم داخل السجل، واستبدل
            rec["full_text_old"] = old
            rec["full_text"] = new
            rec["reocr"] = {"old_q": round(old_q, 1), "new_q": round(new_q, 1),
                            "delta": round(new_q - old_q, 1), "engine": "tesseract-ara", "dpi": RP.DPI,
                            "date": TODAY, "replaced": True}
            replaced += 1
        comp.append({"fid": fid[:8], "title": c["title"][:40], "status": "تمت المعالجة",
                     "old_q": round(old_q, 1), "new_q": round(new_q, 1), "delta": round(new_q - old_q, 1),
                     "decision": "استبدال" if do else "إبقاء القديم (دون العتبة)"})
        modlog.append("- %s «%s»: قديم=%.1f جديد=%.1f Δ=%.1f → %s" % (
            fid[:8], c["title"][:40], old_q, new_q, new_q - old_q, "استبدال" if do else "إبقاء"))

    # اكتب المصدر المحدّث
    with open(JSONL, "w", encoding="utf-8") as f:
        for r in recs:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    # تقارير
    if rows:
        with open(OUT / "document_text_quality_report.csv", "w", encoding="utf-8-sig", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0].keys())); w.writeheader(); w.writerows(rows)
    with open(OUT / "old_vs_new_comparison.csv", "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["fid", "title", "status", "old_q", "new_q", "delta", "decision"])
        w.writeheader(); w.writerows(comp)
    (OUT / "reocr_pages_report.md").write_text(
        "# تقرير الصفحات المُعاد لها OCR\n\n> مخرج آلي يحتاج مراجعة بشرية.\n\n"
        "المحرّك: Tesseract (ara) محلي · DPI=%d · %s\nصفحات أُعيد OCR لها: %d · وثائق مُستبدَلة: %d من %d.\n" % (
            RP.DPI, TODAY, len(rows), replaced, len(cands)), encoding="utf-8")
    (OUT / "modifications_log.md").write_text(
        "# سجل التعديلات — تعميم إعادة OCR\n\n> مخرج آلي يحتاج مراجعة بشرية.\n\n"
        "قاعدة الاستبدال: (جودة الجديد − القديم) > delta=%.0f؛ النص القديم محفوظ في الحقل full_text_old.\n"
        "نسخة احتياطية من المصدر في outputs/reocr_update/_backup/.\n\n## القرارات\n%s\n" % (
            DELTA, "\n".join(modlog)), encoding="utf-8")
    print("وثائق مُعالَجة:", sum(1 for c in comp if c["status"] == "تمت المعالجة"),
          "| مُستبدَلة:", replaced, "| صفحات:", len(rows), "| تعذّر:", sum(1 for c in comp if "تعذّر" in c["status"]))


if __name__ == "__main__":
    main()
