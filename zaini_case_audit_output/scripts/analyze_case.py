#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
analyze_case.py
تحليلات قانونية مساعِدة (آلية - تحتاج مراجعة بشرية) فوق نتائج الفحص:
  1) خط زمني للقضية: كل تاريخ هجري/ميلادي مع الملف المصدر ونوعه.
  2) جدول المبالغ المركزية مع الملفات التي وردت فيها.
  3) أسباب الاعتراض/النقض المرشّحة (من نص الدراسة والمستندات).
  4) جدول الإحالات النظامية المركزية (نظام + مادة) مع مصادرها.

كل المخرجات موسومة [مخرج آلي / Script Output - سماوي] و[يحتاج مراجعة بشرية - وردي].
الاستخدام: python3 analyze_case.py --staging <staging_dir>
"""
import argparse
import csv
import json
import re
from collections import defaultdict, Counter
from pathlib import Path

import audit_zaini_case as AZ  # إعادة استخدام التطبيع والتعابير النمطية

TAG_S = AZ.TAG_SCRIPT
TAG_R = AZ.TAG_NEEDS_REVIEW
OUT_CSV = AZ.OUT_CSV
OUT_XLSX = AZ.OUT_XLSX
OUT_MD = AZ.OUT_MD


def hijri_key(d):
    m = re.search(r"(1[34]\d{2})\D+(\d{1,2})\D+(\d{1,2})", d)
    if m:
        y, mo, da = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if mo > 12 or da > 31:  # ترتيب dd/mm/yyyy
            m2 = re.search(r"(\d{1,2})\D+(\d{1,2})\D+(1[34]\d{2})", d)
            if m2:
                da, mo, y = int(m2.group(1)), int(m2.group(2)), int(m2.group(3))
        return y * 10000 + mo * 100 + da
    return 0


def greg_key(d):
    m = re.search(r"((?:19|20)\d{2})\D+(\d{1,2})\D+(\d{1,2})", d)
    if m:
        return int(m.group(1)) * 10000 + int(m.group(2)) * 100 + int(m.group(3))
    m = re.search(r"(\d{1,2})\D+(\d{1,2})\D+((?:19|20)\d{2})", d)
    if m:
        return int(m.group(3)) * 10000 + int(m.group(2)) * 100 + int(m.group(1))
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--staging", default=str(AZ.DEFAULT_STAGING))
    args = ap.parse_args()

    records = AZ.load_from_staging(args.staging, AZ.logging.getLogger("analyze"))
    files = [r for r in records if not r.get("is_folder")]

    # -----------------------------------------------------------------
    # 1) الخط الزمني
    # -----------------------------------------------------------------
    hijri_rows, greg_rows = [], []
    seen_h, seen_g = set(), set()
    for r in files:
        raw = r.get("_text", "") or ""
        if not raw:
            continue
        norm = AZ.normalize_arabic(raw)
        title = r.get("title", "")
        dt = AZ.classify_doc_type(title, norm)
        path = r.get("parent_path", "")
        for m in AZ.RE_HIJRI.finditer(norm):
            d = m.group(0).strip()
            k = (d, title)
            if k in seen_h:
                continue
            seen_h.add(k)
            hijri_rows.append([d, hijri_key(d), title, dt, path, TAG_S, TAG_R])
        for m in AZ.RE_GREG.finditer(norm):
            d = m.group(0).strip()
            k = (d, title)
            if k in seen_g:
                continue
            seen_g.add(k)
            greg_rows.append([d, greg_key(d), title, dt, path, TAG_S, TAG_R])
    hijri_rows.sort(key=lambda x: x[1])
    greg_rows.sort(key=lambda x: x[1])

    # -----------------------------------------------------------------
    # 2) المبالغ المركزية مع مصادرها
    # -----------------------------------------------------------------
    amount_src = defaultdict(set)
    amount_count = Counter()
    for r in files:
        raw = r.get("_text", "") or ""
        if not raw:
            continue
        ents, _ = AZ.extract_entities(raw)
        for a in ents["amounts"]:
            amount_src[a].add(r.get("title", ""))
            amount_count[a] += 1
    amount_rows = []
    for a in sorted(amount_src, key=lambda x: int(re.sub(r"[^\d]", "", x) or 0), reverse=True):
        digits = re.sub(r"[^\d]", "", a)
        if len(digits) < 6:  # ركّز على المبالغ الكبيرة ذات الدلالة
            continue
        srcs = sorted(amount_src[a])
        amount_rows.append([a, amount_count[a], len(srcs), " | ".join(srcs[:6]),
                            TAG_S, TAG_R])

    # -----------------------------------------------------------------
    # 3) أسباب الاعتراض/النقض المرشّحة (من نص الدراسة والمستندات)
    # -----------------------------------------------------------------
    study_txt = ""
    sp = Path(args.staging) / "study" / "study.txt"
    if sp.exists():
        study_txt = sp.read_text(encoding="utf-8", errors="replace")
    grounds = []
    # عناوين مرجعية في الدراسة، نلتقط البنود التي تليها (مصدر نصّي نظيف بترتيب منطقي)
    study_lines = [l.strip() for l in study_txt.split("\n")]
    anchors = [
        (r"أسس\s+اعتراضه\s+على\s+الأسباب", "أسباب اعتراض المدعي"),
        (r"مستند[ًا]?\s+إلى\s+الأسباب\s+التالية", "أسباب صك الحكم"),
        (r"اقتراحات\s+لنقض\s+حجية\s+التقرير\s+المحاسبي", "نقض حجية التقرير المحاسبي"),
        (r"التوصيات\s+الإضافية\s+للسير\s+في\s+طعن\s+النقض", "توصيات السير في طعن النقض"),
        (r"محاور\s+المرافعة\s+المقترحة", "محاور المرافعة المقترحة"),
        (r"الدفوع", "دفوع"),
    ]
    for i, line in enumerate(study_lines):
        for pat, label in anchors:
            if re.search(pat, line):
                # التقط حتى 14 بنداً تالياً ذات طول معقول حتى عنوان/فراغ كبير
                taken = 0
                for j in range(i + 1, min(i + 30, len(study_lines))):
                    s = study_lines[j].strip()
                    if not s:
                        if taken:
                            break
                        continue
                    if len(s) > 600 or re.match(r"^(أولاً|ثانياً|ثالثاً|رابعاً)[:\s]", s) and taken > 6:
                        break
                    if 12 < len(s) < 500:
                        grounds.append([s[:480], label, TAG_S, TAG_R])
                        taken += 1
                    if taken >= 14:
                        break
    # إزالة التكرار التقريبي
    uniq, seen_g2 = [], set()
    for g in grounds:
        key = re.sub(r"\s+", " ", g[0])[:50]
        if key in seen_g2:
            continue
        seen_g2.add(key)
        uniq.append(g)
    grounds = uniq[:80]

    # -----------------------------------------------------------------
    # 4) الإحالات النظامية المركزية
    # -----------------------------------------------------------------
    law_src = defaultdict(set)
    for r in files:
        raw = r.get("_text", "") or ""
        if not raw:
            continue
        ents, _ = AZ.extract_entities(raw)
        for ln in ents["law_names"]:
            law_src[("نظام", ln)].add(r.get("title", ""))
        for art in ents["articles"]:
            law_src[("مادة", art)].add(r.get("title", ""))
    law_rows = []
    for (kind, val), srcs in sorted(law_src.items(), key=lambda kv: -len(kv[1])):
        law_rows.append([kind, val, len(srcs), " | ".join(sorted(srcs)[:5]),
                         "يحتاج تحقق رسمي", TAG_S, TAG_R])

    # -----------------------------------------------------------------
    # كتابة المخرجات
    # -----------------------------------------------------------------
    def wcsv(path, header, rows):
        with open(path, "w", encoding="utf-8-sig", newline="") as f:
            w = csv.writer(f)
            w.writerow(header)
            w.writerows(rows)

    h_tl = ["التاريخ", "مفتاح الترتيب", "الملف المصدر", "نوع المستند", "المسار", "وسم آلي", "وسم مراجعة"]
    h_am = ["المبلغ (ريال)", "تكرار", "عدد الملفات", "أمثلة الملفات المصدر", "وسم آلي", "وسم مراجعة"]
    h_gr = ["السبب/الوجه المرشّح", "المصدر", "وسم آلي", "وسم مراجعة"]
    h_lw = ["النوع", "القيمة", "عدد الملفات", "أمثلة المصادر", "الحالة", "وسم آلي", "وسم مراجعة"]

    wcsv(OUT_CSV / "08_timeline_hijri.csv", h_tl, hijri_rows)
    wcsv(OUT_CSV / "08_timeline_gregorian.csv", h_tl, greg_rows)
    wcsv(OUT_CSV / "09_central_amounts.csv", h_am, amount_rows)
    wcsv(OUT_CSV / "10_objection_cassation_grounds.csv", h_gr, grounds)
    wcsv(OUT_CSV / "11_central_law_references.csv", h_lw, law_rows)

    AZ.write_excel_sheets(OUT_XLSX / "08_case_analysis.xlsx", [
        ("الخط الزمني هجري", h_tl, hijri_rows),
        ("الخط الزمني ميلادي", h_tl, greg_rows),
        ("المبالغ المركزية", h_am, amount_rows),
        ("أسباب الاعتراض-النقض", h_gr, grounds),
        ("الإحالات النظامية", h_lw, law_rows),
    ], set())

    # تقرير Markdown
    md = ["# تحليل القضية: خط زمني وأسباب نقض ومبالغ مركزية", "",
          f"{TAG_S} {TAG_R}", "",
          "> تحليلات آلية مساعِدة لا تُعد رأياً قانونياً نهائياً؛ تتطلب مراجعة بشرية.", "",
          f"## 1) الخط الزمني (هجري) — {len(hijri_rows)} مدخلاً",
          "| التاريخ | الملف | النوع |", "|---|---|---|"]
    for row in hijri_rows[:40]:
        md.append(f"| {row[0]} | {row[2][:55]} | {row[3]} |")
    md += ["", f"## 2) الخط الزمني (ميلادي) — {len(greg_rows)} مدخلاً",
           "| التاريخ | الملف | النوع |", "|---|---|---|"]
    for row in greg_rows[:25]:
        md.append(f"| {row[0]} | {row[2][:55]} | {row[3]} |")
    md += ["", f"## 3) المبالغ المركزية — {len(amount_rows)}",
           "| المبلغ | تكرار | عدد الملفات |", "|---|---|---|"]
    for row in amount_rows[:25]:
        md.append(f"| {row[0]} | {row[1]} | {row[2]} |")
    md += ["", f"## 4) أسباب الاعتراض/النقض المرشّحة — {len(grounds)}",
           "(مستخرجة آلياً من الدراسة والمستندات — تحتاج تدقيقاً)"]
    for g in grounds[:30]:
        md.append(f"- {g[0]}  _(المصدر: {g[1]})_")
    md += ["", f"## 5) الإحالات النظامية المركزية — {len(law_rows)}",
           "| النوع | القيمة | عدد الملفات |", "|---|---|---|"]
    for row in law_rows[:30]:
        md.append(f"| {row[0]} | {row[1]} | {row[2]} |")
    md += ["", "> جميع البنود أعلاه: " + TAG_S + " " + TAG_R]
    (OUT_MD / "case_timeline_and_grounds.md").write_text("\n".join(md), encoding="utf-8")

    print(f"الخط الزمني: هجري {len(hijri_rows)} / ميلادي {len(greg_rows)}")
    print(f"المبالغ المركزية: {len(amount_rows)} | أسباب مرشّحة: {len(grounds)} | إحالات نظامية: {len(law_rows)}")
    print("المخرجات: 08_case_analysis.xlsx + case_timeline_and_grounds.md + CSVs")


if __name__ == "__main__":
    main()
