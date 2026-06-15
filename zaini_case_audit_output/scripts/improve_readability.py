#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
improve_readability.py
يحسّن قراءة النصوص الممسوحة ضوئياً (OCR) التي جاءت بترتيب بصري معكوس:
  - يكتشف الملفات ذات الأشكال التقديمية (presentation forms) العالية.
  - يطبّع (NFKC) ثم يعكس كل سطر لإعادة الترتيب المنطقي، مع إعادة عكس مقاطع
    الأرقام/اللاتيني، وإصلاح الأقواس المعكوسة.
  - يكتب نسخة مقروءة لكل ملف في staging/text_readable/<id>.txt (لا يلمس الأصل).
الاستخدام: python3 improve_readability.py <staging_dir>
"""
import sys
import re
import unicodedata
from pathlib import Path

STAGING = Path(sys.argv[1] if len(sys.argv) > 1 else "staging")
SRC = STAGING / "text"
DST = STAGING / "text_readable"
DST.mkdir(parents=True, exist_ok=True)

PF = re.compile(r"[ﭐ-﷿ﹰ-﻿]")  # أشكال عربية تقديمية
LTR_RUN = re.compile(r"[0-9A-Za-z٠-٩@._\-/:]+")
MIRROR = {"(": ")", ")": "(", "[": "]", "]": "[", "{": "}", "}": "{",
          "<": ">", ">": "<", "«": "»", "»": "«"}


def fix_ltr_runs(s):
    # بعد عكس السطر، تعود مقاطع الأرقام/اللاتيني معكوسة → نعيد عكسها لتصحّ
    return LTR_RUN.sub(lambda m: m.group(0)[::-1], s)


def deobfuscate_line(line):
    norm = unicodedata.normalize("NFKC", line)
    rev = norm[::-1]
    rev = fix_ltr_runs(rev)
    rev = "".join(MIRROR.get(c, c) for c in rev)
    return rev


def is_visual(text):
    """يُعدّ النص بصرياً معكوساً إذا احتوى نسبة معتبرة من الأشكال التقديمية."""
    pf = len(PF.findall(text))
    letters = sum(1 for c in text if c.isalpha())
    return letters > 0 and (pf / letters) > 0.10


def main():
    import json
    fixed = copied = 0
    fixed_ids = []
    for p in sorted(SRC.glob("*.txt")):
        raw = p.read_text(encoding="utf-8", errors="replace")
        out = DST / p.name
        if is_visual(raw):
            lines = raw.split("\n")
            new = "\n".join(deobfuscate_line(l) if l.strip() else "" for l in lines)
            out.write_text(new, encoding="utf-8")
            fixed += 1
            fixed_ids.append(p.stem)
        else:
            out.write_text(raw, encoding="utf-8")
            copied += 1
    (DST / "_fixed_ids.json").write_text(json.dumps(fixed_ids, ensure_ascii=False), encoding="utf-8")
    print(f"نسخ مقروءة: {fixed + copied} (أُصلح ترتيبها: {fixed} / نُسخت كما هي: {copied})")
    print(f"المخرجات في: {DST}")


if __name__ == "__main__":
    main()
