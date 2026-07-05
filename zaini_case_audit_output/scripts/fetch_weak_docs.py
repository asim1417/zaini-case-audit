#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
fetch_weak_docs.py — تنزيل الوثائق الضعيفة فقط من Google Drive تمهيداً لإعادة OCR عبر Azure.

يقرأ full_documents.jsonl → يختار الوثائق التي جودتها دون العتبة (الأسوأ أولاً) →
ينزّل كل واحدة من Drive بمعرّفها إلى staging/reocr_batch/<fileId>.pdf →
ويكتب _candidates.json ليلتقطها reocr_generalize. لا يخترع ولا يحذف شيئاً.
المصدر يبقى على جهازك؛ لا يُرفع شيء. ما يتعذّر تنزيله يُطبع برابطه لتنزيله يدوياً.
"""
import os, re, sys, json
from pathlib import Path

ROOT = Path(os.environ.get("CASE_ROOT") or Path(__file__).resolve().parent.parent)
sys.path.insert(0, str(ROOT / "scripts"))
import reocr_pilot as RP

JSONL = ROOT / "outputs" / "json" / "full_documents.jsonl"
BATCH = ROOT / "staging" / "reocr_batch"
CAND = ROOT / "outputs" / "reocr_pilot" / "_candidates.json"
TARGETS = ROOT / "staging" / "_reocr_targets.json"   # قائمة أهداف صريحة (إن وُجدت تُستخدم مباشرة)
Q_THRESH = float(os.environ.get("REOCR_QUALITY_THRESHOLD", "60"))
MAX_DOCS = int(os.environ.get("REOCR_MAX_DOCS", "0") or "0")  # 0 = بلا حدّ

FID_RE = re.compile(r"/d/([A-Za-z0-9_-]+)")


def fid_of(rec):
    m = FID_RE.search(rec.get("viewUrl", "") or "")
    return m.group(1) if m else None


def select(recs):
    # (1) أهداف صريحة مضبوطة مسبقاً (الـ17/9 وثيقة المحدّدة) — الأولوية لها.
    if TARGETS.exists():
        tg = json.load(open(TARGETS, encoding="utf-8"))
        out = [{"fid": t["fid"], "title": t.get("title", ""),
                "old_q": t.get("q", 0), "viewUrl": t.get("viewUrl", "")} for t in tg if t.get("fid")]
        print("استُخدمت قائمة الأهداف الصريحة: %d وثيقة (%s)" % (len(out), TARGETS.name))
        return out[:MAX_DOCS] if MAX_DOCS > 0 else out
    # (2) وإلا: اختيار تلقائي حسب عتبة الجودة.
    out = []
    for r in recs:
        fid = fid_of(r)
        if not fid:
            continue
        ft = r.get("full_text", "") or ""
        q = RP.quality_metrics(ft)["quality"] if ft.strip() else 0.0
        if q < Q_THRESH:
            out.append({"fid": fid, "title": (r.get("title", "") or ""),
                        "old_q": round(q, 1), "viewUrl": r.get("viewUrl", "")})
    out.sort(key=lambda c: c["old_q"])
    return out[:MAX_DOCS] if MAX_DOCS > 0 else out


def download(fid, dest):
    if dest.exists() and dest.stat().st_size > 0:
        return True, "موجود مسبقاً"
    try:
        import gdown
    except Exception:
        return False, "gdown غير مثبّت (pip install gdown)"
    url = "https://drive.google.com/uc?id=%s" % fid
    last = ""
    # جرّب مع fuzzy (gdown الحديث) ثم بدونه (الإصدارات الأقدم) — لا نفترض توقيعاً واحداً.
    for kw in ({"fuzzy": True}, {}):
        try:
            gdown.download(url, str(dest), quiet=True, **kw)
            if dest.exists() and dest.stat().st_size > 0:
                return True, "نُزّل"
            last = "تعذّر (قد يكون غير مشارَك للعموم — نزّله يدوياً)"
        except TypeError:
            continue  # هذا الإصدار لا يدعم fuzzy — أعد المحاولة بدونه
        except Exception as e:
            last = "فشل: %s" % str(e)[:80]
    return False, last or "تعذّر التنزيل"


def main():
    BATCH.mkdir(parents=True, exist_ok=True)
    CAND.parent.mkdir(parents=True, exist_ok=True)
    if not JSONL.exists():
        print("✗ لم يُعثر على بيانات الحزمة:", JSONL); sys.exit(1)
    recs = [json.loads(l) for l in open(JSONL, encoding="utf-8") if l.strip()]
    cands = select(recs)
    print("اختير %d وثيقة دون عتبة الجودة %.0f (الأسوأ أولاً)%s" % (
        len(cands), Q_THRESH, (" — حدّ الجولة %d" % MAX_DOCS) if MAX_DOCS else ""))
    ok, fail = [], []
    for c in cands:
        good, note = download(c["fid"], BATCH / (c["fid"] + ".pdf"))
        print("  %s %-38s %s" % ("✓" if good else "✗", c["title"][:38], note))
        (ok if good else fail).append(c)
    # نكتب فقط ما توفّر فعلاً ليعالجه reocr_generalize (وما تعذّر يبقى للتنزيل اليدوي).
    json.dump(cands, open(CAND, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print("\nجاهز للمعالجة: %d | تعذّر تنزيله: %d" % (len(ok), len(fail)))
    if fail:
        print("نزّل المتعذّرة يدوياً إلى %s باسم <المعرّف>.pdf:" % BATCH)
        for c in fail:
            print("  - %s\n      المعرّف: %s\n      الرابط: %s" % (
                c["title"][:60], c["fid"], c.get("viewUrl") or "(غير متوفّر)"))


if __name__ == "__main__":
    main()
