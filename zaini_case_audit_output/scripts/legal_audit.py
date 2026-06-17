#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
legal_audit.py — واجهة أوامر موحّدة لنظام الفحص القانوني (متعدّد القضايا).

يحوّل النظام من «سكربتات قضية واحدة» إلى أداة عامة: كل قضية مجلد مستقل تحت cases/،
والمحرّك (scripts/) مشترك. يُحدَّد جذر القضية عبر متغيّر البيئة CASE_ROOT تلقائياً.

الأوامر:
  python3 scripts/legal_audit.py new  <اسم_القضية>     # إنشاء هيكل قضية جديدة
  python3 scripts/legal_audit.py run  <اسم_القضية>     # تشغيل الفحص الكامل على القضية
  python3 scripts/legal_audit.py list                  # عرض القضايا الموجودة

بعد new: ضع نصوص المستندات في cases/<اسم>/staging/text و parts، وعدّل case_config.json،
(واختيارياً ضع دراسة بروابط في staging/study/source_study.docx)، ثم شغّل run.
"""
import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
PKG_ROOT = SCRIPT_DIR.parent              # zaini_case_audit_output
CASES_DIR = PKG_ROOT / "cases"

CONFIG_TEMPLATE = {
    "_تعليق": "عدّل هذا الملف بمعطيات قضيتك ثم شغّل: legal_audit.py run <اسم_القضية>",
    "case": {"number": "", "other_numbers": [], "title": "", "case_folder_name": ""},
    "deed_numbers_known": [],
    "parties": {"اسم الطرف": ["أنماط مطابقة الاسم"]},
    "other_actors": {},
    "company_patterns": [],
}


def case_dir(name):
    return CASES_DIR / name


def cmd_new(name):
    d = case_dir(name)
    for sub in ("staging/text", "staging/parts", "staging/study", "staging/raw"):
        (d / sub).mkdir(parents=True, exist_ok=True)
    cfg = d / "case_config.json"
    if not cfg.exists():
        cfg.write_text(json.dumps(CONFIG_TEMPLATE, ensure_ascii=False, indent=2),
                       encoding="utf-8")
    print(f"أُنشئت القضية: {d}")
    print("الخطوات التالية:")
    print(f"  1) ضع نصوص المستندات في: {d}/staging/text/<id>.txt")
    print(f"     وبياناتها الوصفية (JSONL) في: {d}/staging/parts/*.jsonl")
    print(f"  2) عدّل ملف الإعداد: {cfg}")
    print(f"  3) (اختياري) ضع الدراسة في: {d}/staging/study/source_study.docx")
    print(f"  4) شغّل:  python3 scripts/legal_audit.py run {name}")


def _run(step, args, env):
    print(f"\n>> {step}")
    r = subprocess.run([sys.executable, str(SCRIPT_DIR / args[0])] + args[1:], env=env)
    if r.returncode != 0:
        print(f"   تحذير: {step} انتهى برمز {r.returncode}")


def cmd_run(name):
    d = case_dir(name)
    if not (d / "staging").exists():
        print(f"خطأ: القضية غير موجودة: {d}. أنشئها أولاً بـ new.")
        sys.exit(1)
    staging = str(d / "staging")
    env = dict(os.environ)
    env["CASE_ROOT"] = str(d)            # يوجّه مخرجات المحرّك إلى مجلد القضية
    cfg = d / "case_config.json"
    if cfg.exists():
        env["CASE_CONFIG"] = str(cfg)

    # تلقائياً: عالج أي ملفات ثنائية (أرشيفات/صور/PDF خام) إن وُجدت في staging/raw
    raw = d / "staging" / "raw"
    if raw.exists() and any(raw.iterdir()):
        _run("معالجة الملفات الثنائية (فكّ ضغط + OCR)", ["process_binaries.py", staging], env)
    _run("تحسين قراءة النصوص", ["improve_readability.py", staging], env)
    study = d / "staging" / "study" / "source_study.docx"
    if study.exists():
        _run("بناء فهرس الدراسة", ["build_study_index.py", str(study), staging], env)
    _run("الفحص الآلي", ["audit_zaini_case.py", "--staging", staging], env)
    _run("التحليل", ["analyze_case.py", "--staging", staging], env)
    _run("الموجز وسجل الصكوك", ["case_brief.py", "--staging", staging], env)
    _run("توليد Word", ["make_word.py", "--staging", staging], env)
    _run("الفهرس الرئيسي Excel", ["make_master_excel.py", "--staging", staging], env)
    _run("فحص الجودة", ["qc_readability.py", staging], env)
    _run("حزمة المخرجات", ["make_bundle.py"], env)
    print(f"\nاكتمل. المخرجات في: {d}/outputs   والحزمة في: {d}/zaini_outputs_bundle.zip")


def cmd_list():
    if not CASES_DIR.exists():
        print("لا توجد قضايا بعد. أنشئ واحدة بـ: legal_audit.py new <اسم>")
        return
    cases = [p.name for p in sorted(CASES_DIR.iterdir()) if p.is_dir()]
    print(f"القضايا ({len(cases)}):")
    for c in cases:
        print("  -", c)


def main():
    ap = argparse.ArgumentParser(description="نظام الفحص القانوني — أداة متعددة القضايا")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p_new = sub.add_parser("new", help="إنشاء قضية جديدة")
    p_new.add_argument("name")
    p_run = sub.add_parser("run", help="تشغيل الفحص الكامل على قضية")
    p_run.add_argument("name")
    sub.add_parser("list", help="عرض القضايا")
    a = ap.parse_args()
    if a.cmd == "new":
        cmd_new(a.name)
    elif a.cmd == "run":
        cmd_run(a.name)
    elif a.cmd == "list":
        cmd_list()


if __name__ == "__main__":
    main()
