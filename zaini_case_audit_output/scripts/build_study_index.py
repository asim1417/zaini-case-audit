#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
build_study_index.py
بناء فهرس موثوق لجميع ملفات القضية الـ192 مباشرةً من ملف الدراسة (DOCX).
العنوان يُؤخذ بأولوية: العنوان الحقيقي من بيانات Drive (إن توفّر) > وصف صف الجدول
في الدراسة > نص الرابط (إن لم يكن عاماً مثل "فتح الملف") > المعرّف.
القسم (parent_path) يُحدَّد من ترتيب الأقسام في الوثيقة.
يُنتج: staging/parts_clean/study_index.jsonl
"""
import sys, zipfile, re, json, glob, os
from xml.etree import ElementTree as ET
from pathlib import Path

DOCX = sys.argv[1]
STAGING = Path(sys.argv[2])
TEXT = STAGING / "text"
OUTDIR = STAGING / "parts_clean"
OUTDIR.mkdir(parents=True, exist_ok=True)

W = '{http://schemas.openxmlformats.org/wordprocessingml/2006/main}'
RID = '{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id'
GENERIC = {"فتح الملف", "فتح المجلد", "الملف", "رابط", "رابط الملف", "رابط المجلد",
           "اضغط هنا", "هنا", "↗", "عرض"}

z = zipfile.ZipFile(DOCX)
rels = z.read('word/_rels/document.xml.rels').decode('utf-8')
relmap = {m.group(1): m.group(2) for m in
          re.finditer(r'<Relationship[^>]*Id="([^"]+)"[^>]*Target="([^"]+)"', rels)}
root = ET.fromstring(z.read('word/document.xml').decode('utf-8'))
body = root.find(W + 'body')

def file_id(url):
    for pat in (r'/file/d/([A-Za-z0-9_\-]{20,})', r'[?&]id=([A-Za-z0-9_\-]{20,})'):
        m = re.search(pat, url)
        if m:
            return m.group(1)
    return None

def para_text(p):
    return ''.join(t.text or '' for t in p.iter(W + 't')).strip()

def links_in(el):
    out = []
    for hl in el.iter(W + 'hyperlink'):
        fid = file_id(relmap.get(hl.get(RID), ''))
        if fid:
            out.append((fid, ''.join(t.text or '' for t in hl.iter(W + 't')).strip()))
    return out

# إثراء من بيانات الزاحفات (عنوان/حجم/تواريخ حقيقية) بحسب المعرّف
enrich = {}
for jl in glob.glob(str(STAGING / "parts" / "*.jsonl")):
    try:
        for line in open(jl, encoding="utf-8"):
            line = line.strip()
            if not line:
                continue
            r = json.loads(line)
            rid = r.get("id")
            if rid and (rid not in enrich or (r.get("title") and not enrich[rid].get("title"))):
                enrich[rid] = r
    except Exception:
        pass

# مرور مرتّب على عناصر جسم الوثيقة (فقرات وجداول) لتتبّع القسم والتقاط الروابط
ordered = []  # (fid, anchor_text, row_desc, section)
seen = set()
cur_section = "أ. المجلد الرئيسي للقضية"

def consider_section(txt):
    global cur_section
    if 4 < len(txt) < 100 and ('رابط المجلد' not in txt) and (
        re.match(r'^[أ-ي]\s*[-.‎]', txt) or re.search(r'\(\s*\d+\s*مل', txt)):
        cur_section = re.sub(r'\s+', ' ', txt)

for el in list(body):
    tag = el.tag
    if tag == W + 'p':
        txt = para_text(el)
        consider_section(txt)
        for fid, anchor in links_in(el):
            if fid not in seen:
                seen.add(fid); ordered.append([fid, anchor, "", cur_section])
    elif tag == W + 'tbl':
        for tr in el.iter(W + 'tr'):
            # اجمع نص الخلايا وروابطها في هذا الصف
            cell_texts = []
            row_links = []
            for tc in tr.iter(W + 'tc'):
                ct = ' '.join(para_text(p) for p in tc.iter(W + 'p')).strip()
                if ct:
                    cell_texts.append(ct)
                row_links.extend(links_in(tc))
            # الوصف = نص الخلايا غير العامة وغير الرقمية المحضة
            desc_parts = [c for c in cell_texts
                          if c not in GENERIC and not re.fullmatch(r'\d{1,4}', c)]
            row_desc = re.sub(r'\s+', ' ', ' ـ '.join(desc_parts))[:180]
            for fid, anchor in row_links:
                if fid not in seen:
                    seen.add(fid); ordered.append([fid, anchor, row_desc, cur_section])

def pick_title(fid, anchor, row_desc):
    et = (enrich.get(fid, {}) or {}).get("title")
    if et and et.strip() and et.strip() not in GENERIC:
        return et.strip()
    if row_desc and row_desc not in GENERIC:
        return row_desc
    if anchor and anchor not in GENERIC:
        return anchor
    return fid

records = []
for order, (fid, anchor, row_desc, section) in enumerate(ordered, 1):
    e = enrich.get(fid, {})
    title = pick_title(fid, anchor, row_desc)
    ext = (e.get("fileExtension") or "")
    if not ext:
        m = re.search(r'\.([A-Za-z0-9]{2,5})(?:\s|$|\))', title)
        ext = (m.group(1).lower() if m else "")
    tf = TEXT / f"{fid}.txt"
    text_chars = 0
    if tf.exists():
        try:
            text_chars = len(tf.read_text(encoding="utf-8", errors="replace"))
        except Exception:
            text_chars = tf.stat().st_size
    if tf.exists() and text_chars >= 20:
        status, tfile = "ok", str(tf)
    elif tf.exists():
        status, tfile = "empty", str(tf)
    else:
        status, tfile = "not_retrieved", None
    records.append({
        "id": fid, "title": title, "mimeType": e.get("mimeType", ""),
        "fileExtension": ext, "fileSize": e.get("fileSize"),
        "createdTime": e.get("createdTime"), "modifiedTime": e.get("modifiedTime"),
        "viewUrl": e.get("viewUrl") or f"https://drive.google.com/file/d/{fid}/view",
        "owner": e.get("owner"), "parentId": e.get("parentId", ""),
        "parent_path": section, "is_folder": False,
        "text_chars": text_chars, "text_file": tfile,
        "read_status": status, "read_error": e.get("read_error"),
        "study_order": order,
    })

outp = OUTDIR / "study_index.jsonl"
with open(outp, "w", encoding="utf-8") as f:
    for r in records:
        f.write(json.dumps(r, ensure_ascii=False) + "\n")

retrieved = sum(1 for r in records if r["read_status"] == "ok")
real_titles = sum(1 for r in records if r["title"] != r["id"]
                  and r["title"] not in GENERIC)
print(f"records: {len(records)} | text ok: {retrieved} | not retrieved/empty: {len(records)-retrieved}")
print(f"records with a real title: {real_titles}")
print(f"wrote: {outp}")
