#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
reocr_hard.py — محرّك OCR محلي مُعزّز للصفحات الأصعب (بلا أي API).

لكل صفحة يجرّب عدّة متغيّرات معالجة صور (تباين/عتبة Otsu/تكبير+حدّة/إزالة تشويش)
× عدّة أوضاع Tesseract (psm/oem)، ويختار النص الأعلى جودة وفق معادلة الجودة الموثّقة.
يعالج: الوثائق بلا نص (إنشاء) + أدنى وثيقة بعد إعادة OCR (استبدال إن تحسّن).
يحافظ على القديم (full_text_old) ويسجّل الاستراتيجية الفائزة لكل صفحة.
"""
import os, re, sys, csv, json, subprocess, datetime
from pathlib import Path
from PIL import Image, ImageOps, ImageFilter

ROOT = Path(os.environ.get("CASE_ROOT") or Path(__file__).resolve().parent.parent)
sys.path.insert(0, str(ROOT / "scripts"))
import reocr_pilot as RP
try:
    import numpy as np
    HAVE_NP = True
except Exception:
    HAVE_NP = False
from pdf2image import convert_from_path

JSONL = ROOT / "outputs" / "json" / "full_documents.jsonl"
HARD = ROOT / "staging" / "reocr_hard"
BATCH = ROOT / "staging" / "reocr_batch"
OUT = ROOT / "outputs" / "reocr_hard"
TXT = OUT / "ocr_text"
DPI = 400
TODAY = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")

TARGETS = []  # [("<DRIVE_FILE_ID>", "replace"|"new")]


def otsu(gray):
    if not HAVE_NP:
        return gray.point(lambda x: 255 if x > 140 else 0)
    arr = np.asarray(gray); hist = np.bincount(arr.ravel(), minlength=256).astype(float)
    total = arr.size; sumv = float(np.dot(np.arange(256), hist))
    wB = 0.0; sumB = 0.0; mx = 0.0; thr = 127
    for i in range(256):
        wB += hist[i]
        if wB == 0:
            continue
        wF = total - wB
        if wF == 0:
            break
        sumB += i * hist[i]
        mB = sumB / wB; mF = (sumv - sumB) / wF
        between = wB * wF * (mB - mF) ** 2
        if between > mx:
            mx = between; thr = i
    return Image.fromarray(((arr > thr) * 255).astype("uint8"))


def variants(im):
    g = ImageOps.grayscale(im)
    base = ImageOps.autocontrast(g, cutoff=2)
    up = base.resize((int(base.width * 1.5), int(base.height * 1.5)), Image.LANCZOS) \
             .filter(ImageFilter.UnsharpMask(radius=2, percent=150))
    den = ImageOps.autocontrast(g.filter(ImageFilter.MedianFilter(3)), cutoff=2)
    return {"base": base, "otsu": otsu(g), "upscale": up, "denoise": den}


def ocr(im, psm):
    p = OUT / "_t.png"; im.save(p)
    try:
        r = subprocess.run(["tesseract", str(p), "stdout", "-l", "ara", "--oem", "1", "--psm", str(psm)],
                           capture_output=True, text=True, timeout=180)
        return r.stdout or ""
    except Exception:
        return ""


COMBOS = [("base", 6), ("otsu", 6), ("upscale", 4), ("denoise", 6), ("base", 3)]


def best_page_text(im):
    vs = variants(im)
    best_txt, best_q, best_combo = "", -1, ""
    for vname, psm in COMBOS:
        t = ocr(vs[vname], psm)
        q = RP.quality_metrics(t)["quality"]
        if q > best_q:
            best_q, best_txt, best_combo = q, t, "%s/psm%d" % (vname, psm)
    return best_txt, best_q, best_combo


def find_file(fid):
    for d in (HARD, BATCH):
        for ext in (".pdf", ".jpg", ".jpeg", ".png", ".JPG"):
            p = d / (fid + ext)
            if p.exists():
                return p
    return None


def load_pages(path):
    sig = open(path, "rb").read(4)
    if sig[:4] == b"%PDF":
        return convert_from_path(str(path), dpi=DPI)
    return [Image.open(path).convert("RGB")]


def main():
    OUT.mkdir(parents=True, exist_ok=True); TXT.mkdir(exist_ok=True)
    recs = [json.loads(l) for l in open(JSONL, encoding="utf-8") if l.strip()]
    by_fid = {}
    for r in recs:
        m = re.search(r"/d/([\w-]+)", r.get("viewUrl", "") or "")
        if m:
            by_fid[m.group(1)] = r
    rows, comp = [], []
    changed = 0
    for fid, mode in TARGETS:
        rec = by_fid.get(fid); path = find_file(fid)
        if rec is None or path is None:
            comp.append({"fid": fid[:8], "title": (rec or {}).get("title", "?")[:40],
                         "mode": mode, "status": "تعذّر (لم يُنزّل)", "old_q": "", "new_q": ""})
            continue
        try:
            pages = load_pages(path)
        except Exception as e:
            comp.append({"fid": fid[:8], "title": rec.get("title", "")[:40], "mode": mode,
                         "status": "فشل التحويل", "old_q": "", "new_q": ""})
            continue
        new_pages = []
        for pi, im in enumerate(pages, 1):
            t, q, combo = best_page_text(im)
            new_pages.append(t)
            rows.append({"fid": fid[:8], "title": rec.get("title", "")[:40], "صفحة": pi,
                         "الاستراتيجية الفائزة": combo, "جودة": q, "تقدير": RP.grade(q),
                         "كلمات": len(t.split())})
        new = "\n".join(new_pages)
        new_q = RP.quality_metrics(new)["quality"]
        old = rec.get("full_text", "") or ""
        old_q = RP.quality_metrics(old)["quality"] if old.strip() else 0.0
        (TXT / (fid + ".txt")).write_text(new, encoding="utf-8")
        do = (mode == "new" and new.strip()) or (mode == "replace" and new_q - old_q > RP.DELTA)
        if do:
            if old.strip():
                rec["full_text_old"] = rec.get("full_text_old", old)
            rec["full_text"] = new
            rec["reocr"] = {"old_q": round(old_q, 1), "new_q": round(new_q, 1),
                            "delta": round(new_q - old_q, 1), "engine": "tesseract-ara-enhanced",
                            "dpi": DPI, "date": TODAY, "replaced": True}
            changed += 1
        comp.append({"fid": fid[:8], "title": rec.get("title", "")[:40], "mode": mode,
                     "status": "تمّ" + (" (مُحدَّث)" if do else " (بقي القديم)"),
                     "old_q": round(old_q, 1), "new_q": round(new_q, 1)})

    with open(JSONL, "w", encoding="utf-8") as f:
        for r in recs:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    if rows:
        with open(OUT / "hard_pages_quality.csv", "w", encoding="utf-8-sig", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0].keys())); w.writeheader(); w.writerows(rows)
    with open(OUT / "hard_comparison.csv", "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["fid", "title", "mode", "status", "old_q", "new_q"])
        w.writeheader(); w.writerows(comp)
    print("الأهداف:", len(TARGETS), "| مُحدّثة:", changed, "| صفحات:", len(rows), "| numpy:", HAVE_NP)
    for c in comp:
        print("  %s | %s | %s→%s" % (c["status"], c["title"][:34], c["old_q"], c["new_q"]))


if __name__ == "__main__":
    main()
