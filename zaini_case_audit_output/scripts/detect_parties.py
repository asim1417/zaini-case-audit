#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
detect_parties.py — اكتشاف تلقائي لأسماء الأطراف والوكلاء من نصّ القضية نفسه.

يمسح النصوص المقروءة ويلتقط الأسماء عبر قرائن قضائية (المدعي/المدعى عليه/ضد/
وكيلاً عن/الهوية الوطنية...)، ثم يكتب المصطلحات المتكرّرة إلى staging/auto_terms.json
ليحمّلها كاشف اتجاه النص تلقائياً — فيتقوّى المحرّك بلا إدخال يدوي.
الاستخدام: python3 detect_parties.py <staging_dir>
"""
import sys
import re
import json
from collections import Counter
from pathlib import Path

STAGING = Path(sys.argv[1] if len(sys.argv) > 1 else "staging")
RDIR = STAGING / "text_readable"
SRC = RDIR if RDIR.exists() else (STAGING / "text")

AR = r"[؀-ۿ]"
NAME = r"((?:" + AR + r"{2,}\s+){1,4}" + AR + r"{2,})"  # 2–5 كلمات عربية متتابعة
# نقتصر على أقوى القرائن وأقلّها ضوضاء: صفّ جدول الأطراف، والوكالة.
PATTERNS = [
    NAME + r"\s+الهوية\s+الوطنية",          # صفّ جدول الأطراف (الأكثر موثوقية)
    r"وكيل[اً]?\s+عن\s+" + NAME,            # وكيلاً عن فلان
    NAME + r"\s+(?:سعودي|سعوديه)\s+(?:المدعي|مدعى|وكيل|حاضر|محام)",
]
# كلمات شائعة/أفعال لا تُعدّ أسماء أطراف (لتفادي تلويث القاموس)
STOP = set("""المدعي المدعى عليه عليها الهوية الوطنية المحكمة الدائرة القضية الجلسة
وزارة العدل المملكة العربية السعودية بموجب الوكالة الصادرة بصفته بصفتهم الشركة رقم
وبعد وحيث الحمد الله بسم الرحمن الرحيم وقد وفي ولا وهو هذا هذه التي الذي بناء على
أبدى أثار أبرم أجاب أقر قال قرر ذكر أفاد طلب نطلب يطلب حضر صادق المبلغ التاريخ
والده ثم إلى من عن مع كما أن إن ضد تاريخ صك نظام المادة""".split())


def _looks_like_name(toks):
    # اسم شخص محتمل: 2–4 كلمات، كلها ليست من الكلمات الشائعة/الأفعال
    return 2 <= len(toks) <= 4 and all(w not in STOP for w in toks)


def main():
    phrase_cnt = Counter()
    for p in sorted(SRC.glob("*.txt")):
        if p.name.startswith("_"):
            continue
        t = p.read_text(encoding="utf-8", errors="replace")
        for pat in PATTERNS:
            for m in re.finditer(pat, t):
                name = re.sub(r"\s+", " ", m.group(1)).strip()
                toks = [w for w in name.split() if len(w) >= 3]
                if _looks_like_name(toks):
                    phrase_cnt[" ".join(toks)] += 1
    # احتفظ بالأسماء المتكرّرة فقط، ثم استخرج كلماتها المميِّزة (أسماء العائلة/الأعلام)
    names = [ph for ph, c in phrase_cnt.items() if c >= 2]
    toks = Counter()
    for ph in names:
        for w in ph.split():
            if w not in STOP:
                toks[w] += phrase_cnt[ph]
    terms = sorted({w for w, c in toks.items() if c >= 2 and len(w) >= 3} | set(names))
    (STAGING / "auto_terms.json").write_text(
        json.dumps(terms, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"اكتُشف تلقائياً {len(terms)} مصطلح/اسم من النص ⇐ staging/auto_terms.json")
    if terms:
        print("أمثلة:", "، ".join(terms[:15]))


if __name__ == "__main__":
    main()
