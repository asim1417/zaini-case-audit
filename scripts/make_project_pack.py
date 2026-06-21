#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
make_project_pack.py — حزمة نص مهيّأة لمشروع كلود (claude.ai) مع فهرس.

تنتج مجلد outputs/project_pack/ فيه:
  - 00_الفهرس.md        : فهرس كل المستندات (عنوان/نوع/تاريخ/المعرّف/موقع النص).
  - 01_النصوص_جزء1.md … : النص الكامل للمستندات الفريدة، مقسّماً أجزاء ≤ ~1.4MB.

الهدف: إضافة «النص الكامل + فهرسه» داخل معرفة المشروع ضمن حدّ السعة، بحذف النسخ
المكرّرة. تُربط هذه الحزمة بالمشروع عبر GitHub.

المصدر: outputs/json/full_documents.jsonl
كل المخرجات «مساعدة آلية تحتاج مراجعة بشرية».
"""
import os, json
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
OUTPUT_ROOT = Path(os.environ.get("CASE_ROOT") or SCRIPT_DIR.parent)
DOCS_JSONL = OUTPUT_ROOT / "outputs" / "json" / "full_documents.jsonl"
PACK = OUTPUT_ROOT / "outputs" / "project_pack"
PART_LIMIT = 1_400_000  # بايت تقريبية لكل جزء

NOTE = "> مخرج آلي يحتاج مراجعة بشرية — ليس رأياً قانونياً نهائياً.\n\n"


def block(r):
    card = r.get("card", {}) or {}
    head = ("===== مستند | العنوان: %s | النوع: %s | التاريخ: %s | المعرّف: %s | الرابط: %s =====\n" % (
        r.get("title", ""), r.get("doc_type", ""), card.get("التاريخ", ""),
        r.get("id", ""), r.get("viewUrl", "")))
    return head + (r.get("full_text", "") or "").strip() + "\n\n"


def main():
    recs = [json.loads(l) for l in DOCS_JSONL.open(encoding="utf-8") if l.strip()]
    seen = {}
    index = []          # كل المستندات للفهرس
    parts = [[]]        # قوائم بلوكات لكل جزء
    sizes = [0]

    for r in recs:
        t = (r.get("full_text", "") or "").strip()
        card = r.get("card", {}) or {}
        row = {
            "title": r.get("title", ""), "type": r.get("doc_type", ""),
            "date": card.get("التاريخ", ""), "id": r.get("id", ""),
        }
        if not t:
            row["loc"] = "صورة/بلا نص مستخرج"
            index.append(row); continue
        key = t  # تطابق حرفي كامل فقط — لا نحذف إلا النسخة المطابقة 100% لتفادي فقد محتوى فريد
        if key in seen:
            row["loc"] = "نسخة مطابقة تماماً (نصّها في «%s»)" % seen[key]
            index.append(row); continue
        b = block(r)
        if sizes[-1] and sizes[-1] + len(b.encode("utf-8")) > PART_LIMIT:
            parts.append([]); sizes.append(0)
        parts[-1].append(b); sizes[-1] += len(b.encode("utf-8"))
        partname = "الجزء %d" % len(parts)
        seen[key] = r.get("title", "")
        row["loc"] = partname
        index.append(row)

    PACK.mkdir(parents=True, exist_ok=True)
    # امسح القديم
    for old in PACK.glob("*.md"):
        old.unlink()

    # اكتب الأجزاء
    for i, blocks in enumerate(parts, 1):
        fn = PACK / ("%02d_النصوص_جزء%d.md" % (i, i))
        fn.write_text("# النصوص الكاملة — الجزء %d\n\n%s%s" % (i, NOTE, "".join(blocks)),
                      encoding="utf-8")

    # اكتب الفهرس
    lines = ["# فهرس مستندات القضية\n", NOTE,
             "عدد المستندات: %d — منها %d بنص فريد، والباقي نسخ مكرّرة أو صور.\n" % (
                 len(index), sum(1 for x in index if x["loc"].startswith("الجزء"))),
             "\n| # | العنوان | النوع | التاريخ | موقع النص |",
             "|---|---|---|---|---|"]
    for n, x in enumerate(index, 1):
        title = x["title"].replace("|", "/")
        lines.append("| %d | %s | %s | %s | %s |" % (n, title, x["type"], x["date"], x["loc"]))
    (PACK / "00_الفهرس.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    total = sum(sizes)
    print("project_pack ready:", PACK)
    print("أجزاء النص:", len(parts), "| الحجم الكلي: %.1f MB" % (total / 1048576))
    print("الفهرس: %d مستند" % len(index))


if __name__ == "__main__":
    main()
