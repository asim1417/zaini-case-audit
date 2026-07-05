#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
make_bundle.py
يبني حزمة ZIP من مجلد outputs مع ضبط علم UTF-8 لأسماء الملفات،
حتى تظهر الأسماء العربية صحيحة عند فكّ الضغط على ويندوز.
الاستخدام: python3 make_bundle.py
المخرج: case_outputs_bundle.zip في جذر المخرجات.
"""
import os
import zipfile
from pathlib import Path

ROOT = Path(os.environ.get("CASE_ROOT") or Path(__file__).resolve().parent.parent)
OUT = ROOT / "case_outputs_bundle.zip"


def main():
    if OUT.exists():
        OUT.remove() if hasattr(OUT, "remove") else os.remove(OUT)
    zf = zipfile.ZipFile(OUT, "w", zipfile.ZIP_DEFLATED)
    targets = [ROOT / "outputs", ROOT / "README.md", ROOT / "NEW_CASE_GUIDE.md"]
    n = 0
    for t in targets:
        if not t.exists():
            continue
        paths = sorted(t.rglob("*")) if t.is_dir() else [t]
        for p in paths:
            if p.is_file():
                arc = str(p.relative_to(ROOT))
                zi = zipfile.ZipInfo(arc, date_time=(2026, 1, 1, 0, 0, 0))
                zi.flag_bits |= 0x800  # UTF-8 filename flag (ويندوز يعرض العربية صحيحة)
                zi.compress_type = zipfile.ZIP_DEFLATED
                zf.writestr(zi, p.read_bytes())
                n += 1
    zf.close()
    print(f"أُنشئت الحزمة: {OUT} ({n} ملفاً، {round(OUT.stat().st_size/1e6,1)} MB)")


if __name__ == "__main__":
    main()
