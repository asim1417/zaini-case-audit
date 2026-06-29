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
import azure_engine  # محرّك سحابي اختياري (مُعطّل ما لم يُفعّل صراحةً عبر .env)

BATCH = ROOT / "staging" / "reocr_batch"
JSONL = ROOT / "outputs" / "json" / "full_documents.jsonl"
OUT = ROOT / "outputs" / "reocr_update"
TXT = OUT / "ocr_text"
BACKUP = OUT / "_backup"
CAND = ROOT / "outputs" / "reocr_pilot" / "_candidates.json"
DELTA = 8.0
# انتقائية: لا نعيد OCR لوثيقة جودتها القديمة فوق هذه العتبة (يوفّر صفحات Azure على F0).
Q_THRESH = float(os.environ.get("REOCR_QUALITY_THRESHOLD", "60"))
TODAY = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
# حدّ أقصى لعدد الوثائق في الجولة (0 = بلا حدّ). مفيد لباقة F0 المحدودة.
MAX_DOCS = int(os.environ.get("REOCR_MAX_DOCS", "0") or "0")


def fid_of(rec):
    m = re.search(r"/d/([A-Za-z0-9_-]+)", rec.get("viewUrl", "") or "")
    return m.group(1) if m else None


def build_candidates(recs):
    """يختار تلقائياً وثائق الحزمة الحالية التي جودتها دون العتبة (استكمال لا إعادة بناء).
       يرتّب الأسوأ أولاً ليُستفاد من صفحات Azure على ما يحتاجها فعلاً."""
    out = []
    for r in recs:
        fid = fid_of(r)
        if not fid:
            continue
        ft = r.get("full_text", "") or ""
        q = RP.quality_metrics(ft)["quality"] if ft.strip() else 0.0
        if q < Q_THRESH:
            out.append({"fid": fid, "title": (r.get("title", "") or ""), "old_q": round(q, 1)})
    out.sort(key=lambda c: c["old_q"])
    return out


def main():
    OUT.mkdir(parents=True, exist_ok=True); TXT.mkdir(exist_ok=True); BACKUP.mkdir(exist_ok=True)
    recs = [json.loads(l) for l in open(JSONL, encoding="utf-8") if l.strip()]
    by_fid = {}
    for r in recs:
        fid = fid_of(r)
        if fid:
            by_fid[fid] = r
    # المرشّحون: من ملف صريح إن وُجد، وإلا اختيار تلقائي من بيانات الحزمة الحالية.
    if CAND.exists():
        cands = json.load(open(CAND, encoding="utf-8"))
        print("مرشّحون من _candidates.json:", len(cands))
    else:
        cands = build_candidates(recs)
        CAND.parent.mkdir(parents=True, exist_ok=True)
        json.dump(cands, open(CAND, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
        print("اختيار تلقائي للوثائق دون عتبة الجودة %.0f → %d وثيقة (الأسوأ أولاً)" % (Q_THRESH, len(cands)))
    if MAX_DOCS > 0 and len(cands) > MAX_DOCS:
        print("حدّ الجولة REOCR_MAX_DOCS=%d → معالجة الأسوأ %d فقط؛ الباقي يُؤجَّل لجولة لاحقة." % (MAX_DOCS, MAX_DOCS))
        cands = cands[:MAX_DOCS]
    # نسخة احتياطية من المصدر قبل أي تعديل
    shutil.copy2(JSONL, BACKUP / ("full_documents.%s.jsonl" % datetime.datetime.now().strftime("%Y%m%d_%H%M%S")))

    # اختيار المحرّك: Azure إن كان متاحاً (مفعّل + مفتاح + SDK)، وإلا المحلي.
    USE_AZURE = azure_engine.available()
    print("المحرّك:", "Azure Document Intelligence" if USE_AZURE else "Tesseract محلي معزّز",
          "| عتبة الانتقاء (جودة قديمة <):", Q_THRESH)

    rows, comp, modlog = [], [], []
    replaced = 0
    for c in cands:
        fid = c["fid"]; pdf = BATCH / (fid + ".pdf")
        rec = by_fid.get(fid)
        if rec is not None and rec.get("reocr", {}).get("replaced"):
            continue  # عولِجت سلفاً (idempotency) — لا تُعد المعالجة ولا تُتلِف full_text_old
        if not pdf.exists() or rec is None:
            comp.append({"fid": fid[:8], "title": c["title"][:40], "status": "تعذّر (لم يُنزّل/غير موجود)",
                         "old_q": "", "new_q": "", "delta": "", "decision": "بقي القديم — يحتاج الأصل"})
            continue
        old = rec.get("full_text", "") or ""
        old_q = RP.quality_metrics(old)["quality"]
        # انتقائية: تخطّى الوثائق التي جودتها القديمة كافية أصلاً (لا تُهدر صفحات Azure).
        if old.strip() and old_q >= Q_THRESH:
            comp.append({"fid": fid[:8], "title": c["title"][:40], "status": "تخطّي (جودة كافية)",
                         "old_q": round(old_q, 1), "new_q": "", "delta": "",
                         "decision": "بقي القديم — فوق العتبة %.0f" % Q_THRESH})
            continue

        engine_label, new, new_q = None, None, None
        # المسار 1: Azure (إن كان متاحاً) — يعيد النص الكامل دفعة واحدة.
        if USE_AZURE:
            atext = azure_engine.ocr_text(pdf)
            if atext and atext.strip():
                new = atext
                am = RP.quality_metrics(new)
                new_q = am["quality"]
                engine_label = "azure-document-intelligence"
                rows.append({"fid": fid[:8], "title": c["title"][:40], "صفحة": "كل الصفحات (Azure)",
                             "كلمات": am["words"], "نسبة عربية": am["ar_ratio"], "رموز": am["bad_syms"],
                             "جودة": am["quality"], "تقدير": RP.grade(am["quality"]), "خطر": am["risk"]})

        # المسار 2: المحرّك المحلي (افتراضي، أو تراجع آمن عند فشل/تعذّر Azure).
        if new is None:
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
            engine_label = "tesseract-ara" + ("-fallback" if USE_AZURE else "")

        (TXT / (fid + ".txt")).write_text(new, encoding="utf-8")
        do = (new_q - old_q) > DELTA
        if do:
            # احفظ القديم داخل السجل، واستبدل (لا نُتلِف نسخة قديمة محفوظة سلفاً).
            rec["full_text_old"] = rec.get("full_text_old", old)
            rec["full_text"] = new
            rec["reocr"] = {"old_q": round(old_q, 1), "new_q": round(new_q, 1),
                            "delta": round(new_q - old_q, 1), "engine": engine_label,
                            "dpi": RP.DPI if engine_label.startswith("tesseract") else None,
                            "date": TODAY, "replaced": True}
            replaced += 1
        comp.append({"fid": fid[:8], "title": c["title"][:40], "status": "تمت المعالجة (%s)" % engine_label,
                     "old_q": round(old_q, 1), "new_q": round(new_q, 1), "delta": round(new_q - old_q, 1),
                     "decision": "استبدال" if do else "إبقاء القديم (دون العتبة)"})
        modlog.append("- %s «%s» [%s]: قديم=%.1f جديد=%.1f Δ=%.1f → %s" % (
            fid[:8], c["title"][:40], engine_label, old_q, new_q, new_q - old_q, "استبدال" if do else "إبقاء"))

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
    eng_name = "Azure Document Intelligence (مع تراجع محلي عند التعذّر)" if USE_AZURE else "Tesseract (ara) محلي"
    (OUT / "reocr_pages_report.md").write_text(
        "# تقرير الصفحات المُعاد لها OCR\n\n> مخرج آلي يحتاج مراجعة بشرية.\n\n"
        "المحرّك: %s · DPI(المحلي)=%d · عتبة الانتقاء=%.0f · %s\n"
        "صفحات/وثائق أُعيد OCR لها: %d · وثائق مُستبدَلة: %d من %d.\n" % (
            eng_name, RP.DPI, Q_THRESH, TODAY, len(rows), replaced, len(cands)), encoding="utf-8")
    (OUT / "modifications_log.md").write_text(
        "# سجل التعديلات — تعميم إعادة OCR\n\n> مخرج آلي يحتاج مراجعة بشرية.\n\n"
        "قاعدة الاستبدال: (جودة الجديد − القديم) > delta=%.0f؛ النص القديم محفوظ في الحقل full_text_old.\n"
        "نسخة احتياطية من المصدر في outputs/reocr_update/_backup/.\n\n## القرارات\n%s\n" % (
            DELTA, "\n".join(modlog)), encoding="utf-8")
    print("وثائق مُعالَجة:", sum(1 for c in comp if c["status"] == "تمت المعالجة"),
          "| مُستبدَلة:", replaced, "| صفحات:", len(rows), "| تعذّر:", sum(1 for c in comp if "تعذّر" in c["status"]))


if __name__ == "__main__":
    main()
