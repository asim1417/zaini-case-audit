#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
build_case_db.py — يبني قاعدة بيانات SQLite للقضية من full_documents.jsonl.

ينشئ جدول docs + جدول بحث نصّي كامل FTS5 (عربي مُطبَّع) ليستعلمه الخادم بسرعة،
فتبقى البيانات على الخادم وتُحمَّل الواجهة خفيفة (وثيقة/نتيجة عند الطلب).

الاستخدام:
  python build_case_db.py <full_documents.jsonl> <out_case.db>
أو عبر البيئة: CASE_JSONL=... CASE_DB=... python build_case_db.py
"""
import os, re, sys, json, sqlite3

# تنظيف: إزالة علامات الاتجاه + توحيد الحروف/الأرقام الفارسية إلى العربية (بلا حذف محتوى).
_STRIP = dict.fromkeys([0x200b, 0x200c, 0x200d, 0x200e, 0x200f, 0x202a, 0x202b,
                        0x202c, 0x202d, 0x202e, 0x2066, 0x2067, 0x2068, 0x2069, 0xfeff], None)
_LOOK = {"ھ": "ه", "ہ": "ه", "ۀ": "ه", "ۃ": "ة", "ی": "ي", "ۍ": "ي", "ک": "ك"}
_PDIG = {0x06F0 + i: chr(0x0660 + i) for i in range(10)}


def clean_text(t):
    if not t:
        return t
    t = t.translate(_STRIP)
    for a, b in _LOOK.items():
        t = t.replace(a, b)
    return t.translate(_PDIG)


def norm(s):
    out = []
    for ch in s or "":
        c = ord(ch)
        if 0x064B <= c <= 0x0652 or c in (0x0640, 0x0670):
            continue
        if ch in "أإآٱ":
            out.append("ا")
        elif ch == "ة":
            out.append("ه")
        elif ch == "ى":
            out.append("ي")
        elif ch == "ؤ":
            out.append("و")
        elif ch == "ئ":
            out.append("ي")
        else:
            out.append(ch.lower())
    return "".join(out)


_BAD = re.compile(r"[�□￯]")


def distortion(text):
    syms = len(_BAD.findall(text))
    reps = len(re.findall(r"(\S)\1{3,}", text))
    frags = sum(1 for l in text.split("\n") if 0 < len(l.strip()) <= 2)
    issues = []
    if syms:
        issues.append("رموز غريبة")
    if reps:
        issues.append("تكرار حروف")
    if frags > 5:
        issues.append("فُتات أسطر")
    return "، ".join(issues)


def build(jsonl, db_path):
    if os.path.exists(db_path):
        os.remove(db_path)
    con = sqlite3.connect(db_path)
    con.executescript("""
      CREATE TABLE docs(
        id TEXT PRIMARY KEY, n INTEGER, title TEXT, doc_type TEXT, date TEXT,
        quality TEXT, distorted INTEGER, dist_reason TEXT,
        view_url TEXT, card TEXT, entities TEXT, full_text TEXT, norm_text TEXT);
      CREATE VIRTUAL TABLE fts USING fts5(
        id UNINDEXED, title, body, tokenize='unicode61 remove_diacritics 2');
    """)
    rows = [json.loads(l) for l in open(jsonl, encoding="utf-8") if l.strip()]
    n = 0
    for r in rows:
        n += 1
        ft = clean_text(r.get("full_text", "") or "")
        title_c = clean_text(r.get("title", ""))
        qc = r.get("qc", {}) or {}
        con.execute("INSERT OR REPLACE INTO docs VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)", (
            r.get("id", "") or ("DOC%03d" % n), n, title_c, r.get("doc_type", "غير مصنف"),
            (r.get("card", {}) or {}).get("التاريخ", ""), qc.get("status", ""),
            1 if distortion(ft) else 0, distortion(ft), r.get("viewUrl", ""),
            json.dumps(r.get("card", {}) or {}, ensure_ascii=False),
            json.dumps(r.get("entities", {}) or {}, ensure_ascii=False),
            ft, norm(title_c + "\n" + ft)))
        con.execute("INSERT INTO fts(id,title,body) VALUES (?,?,?)",
                    (r.get("id", "") or ("DOC%03d" % n), norm(title_c), norm(ft)))
    con.commit()
    cnt = con.execute("SELECT COUNT(*) FROM docs").fetchone()[0]
    con.close()
    print("تم بناء قاعدة البيانات: %s | وثائق: %d" % (db_path, cnt))


if __name__ == "__main__":
    jsonl = sys.argv[1] if len(sys.argv) > 1 else os.environ.get("CASE_JSONL", "full_documents.jsonl")
    db = sys.argv[2] if len(sys.argv) > 2 else os.environ.get("CASE_DB", "case.db")
    if not os.path.exists(jsonl):
        print("✗ لم يُعثر على:", jsonl); sys.exit(1)
    build(jsonl, db)
