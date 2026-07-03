#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
case_brief.py
يولّد مخرجاً موحّداً عملياً للمحامي فوق نتائج الفحص:
  1) سجلّ الصكوك/الأحكام (المعروفة من إعداد القضية + ما ظهر) مع حالة العثور والملف المصدر.
  2) خط زمني للمحطات الرئيسية (من عناوين المستندات الموثوقة + تواريخها).
  3) ملخّص قضية موحّد (Markdown) يجمع الأطراف والمحطات والمبالغ وأسباب النقض وحالة التغطية.

كل المخرجات: [مخرج آلي / Script Output - سماوي] [مخرج آلي يحتاج مراجعة بشرية - وردي].
الاستخدام: python3 case_brief.py --staging <staging_dir>
"""
import argparse
import csv
import json
import re
from pathlib import Path

import audit_case as AZ

TAG_S = AZ.TAG_SCRIPT
TAG_R = AZ.TAG_NEEDS_REVIEW
OUT_CSV, OUT_XLSX, OUT_MD, OUT_JSON = AZ.OUT_CSV, AZ.OUT_XLSX, AZ.OUT_MD, AZ.OUT_JSON

DEEDS = {}  # {"رقم الصك": "وصفه"} — اختياري من إعداد القضية

DATE_IN_TITLE = re.compile(r"(\d{1,2}[-/]\d{1,2}[-/]\d{3,4}|\d{3,4}[-/]\d{1,2}[-/]\d{1,2})")
MILESTONE_KW = ["صحيفة دعوى", "صك حكم", "حكم نهائي", "حكم الولاية", "رفض الولاية",
                "رفض الالتماس", "رفض النقض", "نقض", "التماس", "تخارج", "عقد بيع",
                "تنازل", "شكوى", "حجز", "تنفيذ", "إخطار", "اعتراض", "صلح"]


def hkey(d):
    m = re.search(r"(1[34]\d{2})\D+(\d{1,2})\D+(\d{1,2})", d)
    if m:
        return int(m.group(1)) * 10000 + int(m.group(2)) * 100 + int(m.group(3))
    m = re.search(r"(\d{1,2})\D+(\d{1,2})\D+(1[34]\d{2})", d)
    if m:
        return int(m.group(3)) * 10000 + int(m.group(2)) * 100 + int(m.group(1))
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

    data = json.loads((OUT_JSON / "full_audit_data.json").read_text(encoding="utf-8"))
    files = data["files"]
    agg = data["meta"]["aggregates"]
    counts = data["meta"]["counts"]

    # نص كامل لكل ملف (للبحث عن الصكوك في المتن)
    text_by_id = {}
    tdir = Path(args.staging) / "text"
    for f in files:
        p = tdir / f"{f['id']}.txt"
        if p.exists():
            text_by_id[f["id"]] = AZ.normalize_arabic(p.read_text(encoding="utf-8", errors="replace"))

    # ---- 1) سجلّ الصكوك ----
    deed_rows = []
    for num, desc in DEEDS.items():
        in_title, in_body = [], 0
        for f in files:
            if num in AZ.normalize_arabic(f.get("title", "")):
                in_title.append(f["title"])
            if num in text_by_id.get(f["id"], ""):
                in_body += 1
        status = "ظهر آلياً" if (in_title or in_body) else "لم يظهر في المتاح — يلزم تحقق"
        deed_rows.append([num, desc, status, in_body,
                          (in_title[0][:70] if in_title else ""), TAG_S, TAG_R])

    # ---- 2) خط زمني للمحطات الرئيسية (من العناوين) ----
    miles = []
    seen = set()
    for f in files:
        t = f.get("title", "") or ""
        if not any(k in t for k in MILESTONE_KW):
            continue
        m = DATE_IN_TITLE.search(t)
        date = m.group(1) if m else ""
        key = (date, t[:50])
        if key in seen:
            continue
        seen.add(key)
        miles.append([date, hkey(date), t[:110], f.get("doc_type", ""),
                      f.get("parent_path", ""), TAG_S, TAG_R])
    miles.sort(key=lambda x: (x[1] == 0, x[1]))  # المؤرّخة أولاً ثم بالترتيب

    # ---- مبالغ مركزية (من التجميع) مرتبة بالقيمة ----
    amt_sorted = sorted(agg["amounts"].items(),
                        key=lambda kv: int(re.sub(r"[^\d]", "", kv[0]) or 0), reverse=True)
    big_amts = [(k, v) for k, v in amt_sorted if len(re.sub(r"[^\d]", "", k)) >= 8][:15]

    # ---- أسباب النقض من ملف التحليل ----
    grounds = []
    gpath = OUT_CSV / "10_objection_cassation_grounds.csv"
    if gpath.exists():
        with open(gpath, encoding="utf-8-sig") as fh:
            r = csv.reader(fh)
            next(r, None)
            grounds = [row for row in r]

    # ---- كتابة CSV/Excel ----
    def wcsv(path, header, rows):
        with open(path, "w", encoding="utf-8-sig", newline="") as fh:
            w = csv.writer(fh)
            w.writerow(header)
            w.writerows(rows)

    h_deed = ["رقم الصك/الحكم", "الوصف (مبدئي)", "الحالة", "تكرار في المتن", "ملف بالعنوان", "وسم آلي", "وسم مراجعة"]
    h_mile = ["التاريخ", "مفتاح", "المحطة (عنوان المستند)", "النوع", "القسم", "وسم آلي", "وسم مراجعة"]
    wcsv(OUT_CSV / "12_deeds_register.csv", h_deed, deed_rows)
    wcsv(OUT_CSV / "13_key_milestones.csv", h_mile, miles)
    AZ.write_excel_sheets(OUT_XLSX / "09_case_brief_register.xlsx", [
        ("سجل الصكوك", h_deed, deed_rows),
        ("المحطات الرئيسية", h_mile, miles),
    ], set())

    # ---- 3) ملخّص القضية الموحّد ----
    md = []
    md.append("# ملخّص القضية — موجز تنفيذي موحّد")
    md.append("")
    md.append(f"{TAG_S} {TAG_R}")
    md.append("")
    md.append("> توليف آلي يجمع مخرجات الفحص؛ ليس رأياً قانونياً نهائياً ويتطلب مراجعة المحامي.")
    md.append("")
    md.append("## الأطراف")
    for k, v in agg["parties"].items():
        md.append(f"- **{k}** (ورد في {v} ملفاً)")
    md.append("")
    pass  # (تفاصيل الشركة محل النزاع تُضاف من إعداد القضية إن لزم)
    md.append("")
    md.append("## حالة التغطية المستندية")
    md.append(f"- إجمالي الملفات المجرودة: **{counts['files']}** عبر الأقسام.")
    md.append(f"- مقروءة نصياً: **{counts['readable']}** | تحتاج OCR/فك ضغط/غير متاحة: **{counts['needs_ocr']}**.")
    md.append("")
    md.append("## سجلّ الصكوك/الأحكام (قائمة التكليف)")
    md.append("| الرقم | الوصف المبدئي | الحالة | تكرار |")
    md.append("|---|---|---|---|")
    for row in deed_rows:
        md.append(f"| {row[0]} | {row[1]} | {row[2]} | {row[3]} |")
    md.append("")
    md.append("## المحطات الرئيسية (مرتّبة)")
    md.append("| التاريخ | المحطة | النوع |")
    md.append("|---|---|---|")
    for row in [r for r in miles if r[1] > 0][:30]:
        md.append(f"| {row[0]} | {row[2][:70]} | {row[3]} |")
    md.append("")
    md.append("## المبالغ المركزية")
    for k, v in big_amts:
        md.append(f"- **{k} ريال** (ورد {v} مرة)")
    md.append("")
    md.append("> ملاحظة: عند تعارض تقييمات/مبالغ بين المستندات، يلزم تحقيق وتوفيق قانوني "
              "بمراجعة بشرية (القيم أعلاه استخراج آلي).")
    md.append("")
    md.append("## أسباب الاعتراض/النقض والدفوع (من الدراسة)")
    for g in grounds[:18]:
        md.append(f"- {g[0]}  _({g[1]})_")
    md.append("")
    md.append("## ما يلزم المراجعة البشرية")
    md.append("- اعتماد التصنيفات والكيانات والمحطات.")
    missing_deeds = "، ".join(sorted(DEEDS)) if DEEDS else ""
    md.append("- التحقق الرسمي من الصكوك المعروفة%s والنصوص النظامية."
              % ((" (خصوصاً %s إن لم تظهر)" % missing_deeds) if missing_deeds else ""))
    md.append("- معالجة أي أرشيفات كبيرة لم تُقرأ آلياً (تنزيل يدوي ثم process_binaries.py).")
    md.append("- التحقق من أي روابط محذوفة/غير متاحة وردت في الدراسة.")
    md.append("")
    md.append(f"---\n_توليف آلي_ — {TAG_S} {TAG_R}")
    (OUT_MD / "00_case_brief.md").write_text("\n".join(md), encoding="utf-8")

    found = sum(1 for r in deed_rows if r[2] == "ظهر آلياً")
    print(f"سجل الصكوك: {found}/{len(deed_rows)} ظهرت | محطات رئيسية: {len(miles)} | أسباب: {len(grounds)}")
    print("المخرجات: 00_case_brief.md + 09_case_brief_register.xlsx + 12/13 CSV")


if __name__ == "__main__":
    main()
