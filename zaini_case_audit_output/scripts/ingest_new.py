#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ingest_new.py — استيعاب الوثائق الجديدة من مجلد القضية (لم تكن في المجموعة).

لكل وثيقة جديدة: OCR محلي معزّز (نفس محرّك reocr_hard) → تصنيف + كيانات + بطاقة،
ثم تُضاف إلى full_documents.jsonl دون المساس بالقائم (تُلحَق في النهاية، فتأخذ
معرّفات DOC تالية تلقائياً عند التوليد). نسخة احتياطية قبل التعديل.
"""
import os, re, sys, json, shutil, datetime
from pathlib import Path

ROOT = Path(os.environ.get("CASE_ROOT") or Path(__file__).resolve().parent.parent)
sys.path.insert(0, str(ROOT / "scripts"))
import reocr_pilot as RP
import reocr_hard as RH
import audit_case as AZ
import make_master_excel as MME
from PIL import Image
from pdf2image import convert_from_path

NEW = ROOT / "staging" / "new_docs.json"
BATCH = ROOT / "staging" / "new_batch"
JSONL = ROOT / "outputs" / "json" / "full_documents.jsonl"
BACKUP = ROOT / "outputs" / "reocr_update" / "_backup"
TODAY = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")

FOLDER = {
    "1HivOtyl1MIY9CG0alFmo4aouGnupuc7h": "محاضر ضبط الجلسات للدعوى 42824717",
    "1dJBxUfBSNi1FwQEPaPTmTiI9JnhYAcWn": "الأحكام الصادرة في القضية 42824717",
    "1MEqXV5RKLNqC-cZHqvHwxREpc42SGyeO": "مرفقات المدعي بموقع ناجز",
    "1MqvRb940DF0vLBXP66oucVVtDaDmo1nU": "المجلد الرئيسي للقضية",
}


def main():
    recs = [json.loads(l) for l in open(JSONL, encoding="utf-8") if l.strip()]
    have = set()
    for r in recs:
        m = re.search(r"/d/([\w-]+)", r.get("viewUrl", "") or "")
        if m:
            have.add(m.group(1))
    BACKUP.mkdir(parents=True, exist_ok=True)
    shutil.copy2(JSONL, BACKUP / ("full_documents.ingest.%s.jsonl" % datetime.datetime.now().strftime("%Y%m%d_%H%M%S")))
    newdocs = json.load(open(NEW, encoding="utf-8"))
    added, skipped = 0, 0
    log = []
    for f in newdocs:
        fid = f["id"]
        if fid in have:
            continue
        pdf = BATCH / (fid + ".pdf")
        if not pdf.exists():
            log.append("تعذّر (لم يُنزّل): " + f.get("title", "")[:50]); skipped += 1; continue
        try:
            sig = open(pdf, "rb").read(4)
            pages = convert_from_path(str(pdf), dpi=RH.DPI) if sig[:4] == b"%PDF" else [Image.open(pdf).convert("RGB")]
        except Exception as e:
            log.append("فشل التحويل: " + f.get("title", "")[:50]); skipped += 1; continue
        texts = []
        for im in pages:
            t, q, combo = RH.best_page_text(im)
            texts.append(t)
        full = "\n".join(texts)
        q = RP.quality_metrics(full)["quality"]
        title = f.get("title", "")
        norm = AZ.normalize_arabic(full)
        dtype = AZ.classify_doc_type(title, norm)
        ents, _ = AZ.extract_entities(full)
        cf = {"entities": ents, "doc_type": dtype, "title": title,
              "viewUrl": "https://drive.google.com/file/d/%s/view?usp=drivesdk" % fid}
        card = dict(MME.build_card(cf, full))
        rec = {
            "id": fid, "title": title, "doc_type": dtype,
            "parent_path": FOLDER.get(f.get("parent", ""), "مجلد القضية (مُستوعَب)"),
            "viewUrl": cf["viewUrl"], "card": card, "entities": ents,
            "readable": bool(full.strip()), "full_text": full,
            "reocr": {"new_q": round(q, 1), "engine": "tesseract-ara-enhanced", "dpi": RH.DPI,
                      "date": TODAY, "replaced": True, "ingested": True},
        }
        recs.append(rec)
        added += 1
        log.append("أُضيف [%s | جودة %.1f | %d صفحة]: %s" % (dtype, q, len(pages), title[:46]))

    with open(JSONL, "w", encoding="utf-8") as g:
        for r in recs:
            g.write(json.dumps(r, ensure_ascii=False) + "\n")
    rep = ROOT / "outputs" / "reocr_update" / "ingest_report.md"
    rep.write_text("# تقرير استيعاب الوثائق الجديدة\n\n> مخرج آلي يحتاج مراجعة بشرية.\n\n"
                   "المحرّك: Tesseract-ara معزّز · %s\nأُضيفت: %d · تعذّر: %d · الإجمالي بعد الاستيعاب: %d\n\n## التفصيل\n%s\n" % (
                       TODAY, added, skipped, len(recs), "\n".join("- " + x for x in log)), encoding="utf-8")
    print("أُضيف:", added, "| تعذّر:", skipped, "| الإجمالي:", len(recs))


if __name__ == "__main__":
    main()
