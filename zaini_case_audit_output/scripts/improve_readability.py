#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
improve_readability.py
يحسّن قراءة النصوص الممسوحة/المعكوسة الترتيب (OCR بترتيب بصري) — سطراً بسطر:
  - يكتشف كل سطر معكوس عبر إشارتين: (أ) وجود أشكال عربية تقديمية، أو
    (ب) غلبة كلمات مفتاحية بصيغتها المعكوسة على الصيغة الصحيحة في السطر.
  - يطبّع (NFKC) ويعكس السطر المعكوس فقط، مع إعادة عكس الأرقام/اللاتيني وإصلاح الأقواس.
  - يبقي الأسطر الصحيحة كما هي (يدعم الملفات المختلطة: جزء معكوس وجزء سليم).
  - يكتب نسخة مقروءة لكل ملف في staging/text_readable/<id>.txt (لا يلمس الأصل).
الاستخدام: python3 improve_readability.py <staging_dir>
"""
import sys
import re
import json
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

# كلمات مفتاحية مميِّزة (تتجنّب الهمزات) + صيغتها المعكوسة
NORMAL_MARKERS = ["الله", "المحكمة", "التي", "الذي", "الحكم", "الدعوى", "تاريخ",
                  "الرحيم", "الرحمن", "نظام", "زيني", "رقم", "ريال", "العدل",
                  "الاستئناف", "التجارية", "المدعي", "الشيخ", "صك", "على", "ذلك",
                  "بسم", "عباس", "احمد", "مكتب", "بتاريخ", "والذي", "مليون"]
REVERSED_MARKERS = [m[::-1] for m in NORMAL_MARKERS]


def fix_ltr_runs(s):
    return LTR_RUN.sub(lambda m: m.group(0)[::-1], s)


def reverse_line(norm_line):
    rev = norm_line[::-1]
    rev = fix_ltr_runs(rev)
    rev = "".join(MIRROR.get(c, c) for c in rev)
    return rev


def line_reversed(raw_line, norm_line):
    if PF.search(raw_line):
        return True
    nm = sum(norm_line.count(w) for w in NORMAL_MARKERS)
    rm = sum(norm_line.count(w) for w in REVERSED_MARKERS)
    return rm > nm and rm > 0


def process_text(raw):
    out = []
    fixed_any = False
    for line in raw.split("\n"):
        if not line.strip():
            out.append("")
            continue
        norm = unicodedata.normalize("NFKC", line)
        if line_reversed(line, norm):
            out.append(reverse_line(norm))
            fixed_any = True
        else:
            out.append(norm)
    return "\n".join(out), fixed_any


def main():
    fixed = copied = 0
    fixed_ids = []
    for p in sorted(SRC.glob("*.txt")):
        if p.name.startswith("_"):
            continue
        raw = p.read_text(encoding="utf-8", errors="replace")
        new, fixed_any = process_text(raw)
        (DST / p.name).write_text(new, encoding="utf-8")
        if fixed_any:
            fixed += 1
            fixed_ids.append(p.stem)
        else:
            copied += 1
    (DST / "_fixed_ids.json").write_text(json.dumps(fixed_ids, ensure_ascii=False),
                                         encoding="utf-8")
    print(f"نسخ مقروءة: {fixed + copied} (فيها أسطر صُحِّح ترتيبها: {fixed} / "
          f"سليمة كما هي: {copied})")
    print(f"المخرجات في: {DST}")


if __name__ == "__main__":
    main()
