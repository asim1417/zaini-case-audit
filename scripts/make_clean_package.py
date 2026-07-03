#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
make_clean_package.py — تصدير المنظومة كقالب عام فارغ (بلا أي أسماء أو بيانات قضية).

يبني نسخة قابلة للتوزيع من كامل النظام (المحرّك + الخدمة بإضافاتها السحابية +
مولّد العارض + الوثائق العامة) مع:
  • استبعاد كل ما يخص قضية بعينها (الكتيّب الخاص، تقرير تشغيل القضية).
  • إحلال النسخ العامة من الوثائق، وتفريغ مجلدات البيانات (outputs/staging).
  • إعادة تسمية مجلد المحرّك إلى engine/ وتعديل كل المسارات المُشيرة إليه.
  • تعقيم أي معرّفات خاصة (نقطة Azure الشخصية، اسم خدمة النشر).
  • فحص نهائي بقائمة كلمات محظورة — يفشل البناء إن بقي أي أثر.

الاستخدام:  python scripts/make_clean_package.py [مجلد الإخراج]
الناتج:     <الإخراج>/legal_audit_system/ + legal_audit_system_clean.zip
"""
import re, sys, shutil, zipfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SRC_ENGINE = REPO / "zaini_case_audit_output"
PKG_NAME = "legal_audit_system"

# ملفات خاصة بالقضية — لا تدخل الحزمة إطلاقاً
EXCLUDE_FILES = {
    SRC_ENGINE / "الكتيّب_الرسمي.md",     # نسخة القضية (توجد نسخة عامة تحل محلها)
    SRC_ENGINE / "README.md",             # تقرير تشغيل القضية (أسماء وأرقام)
}

# استبدالات التعقيم في الملفات النصية
REPLACEMENTS = [
    ("zaini_case_audit_output", "engine"),          # مسار المحرّك في الكود والوثائق
    ("aman-legal-ocr", "YOUR-AZURE-RESOURCE"),      # نقطة Azure الشخصية
    ("zaini-case", "legal-audit"),                  # اسم خدمة النشر في render.yaml
    ("audit_zaini_case.py", "audit_case.py"),       # اسم قديم في الوثائق
]

# كلمات محظورة — وجود أيّها في الحزمة النهائية يُفشل البناء
BLOCKLIST = ["زيني", "الزيني", "42824717", "4714689866", "الحجيلان",
             "4731721487", "4731982616", "368,757,931",
             "aman-legal-ocr", "asim1417"]

TEXT_EXTS = {".py", ".md", ".sh", ".ps1", ".yaml", ".yml", ".json", ".txt",
             ".html", ".js", ".css", ".env", ".example", ".template"}


def is_text(p: Path) -> bool:
    return p.suffix.lower() in TEXT_EXTS or p.name in ("Dockerfile", ".env.example")


def sanitize(text: str) -> str:
    for old, new in REPLACEMENTS:
        text = text.replace(old, new)
    return text


def copy_tree(src: Path, dst: Path):
    for p in sorted(src.rglob("*")):
        if p.is_dir() or p in EXCLUDE_FILES or ".git" in p.parts:
            continue
        if "__pycache__" in p.parts or p.suffix == ".pyc":
            continue
        rel = p.relative_to(src)
        out = dst / rel
        out.parent.mkdir(parents=True, exist_ok=True)
        if is_text(p):
            out.write_text(sanitize(p.read_text(encoding="utf-8", errors="replace")),
                           encoding="utf-8")
        else:
            shutil.copy2(p, out)


GENERIC_README = """# نظام الفحص القانوني الآلي — قالب عام فارغ

منظومة متكاملة لتحويل وثائق أي قضية (PDF ممسوح، صور، Word/Excel، أرشيفات) إلى
معرفة منظّمة: فهرس + نصوص مقروءة (OCR عربي معزّز) + بطاقات + خط زمني + تقارير
Word/Excel — مع واجهة تصفّح وخدمة API وربط سحابي بـ Google Drive و OneDrive.

**لا تحتاج أي مفاتيح ذكاء اصطناعي**: القراءة الأساسية محلية ومجانية بالكامل.
المفاتيح الاختيارية (جلب سحابي، OCR أدق عبر Azure) تُفعَّل من الواجهة نفسها.

## البدء السريع (Docker)
```bash
docker build -t legal-audit-service -f service/Dockerfile .
docker run -d -p 8080:8080 -v /srv/legal-jobs:/data/jobs -e API_KEY="سرّي" legal-audit-service
```
ثم افتح `http://HOST:8080/` — واجهة عربية كاملة: التفعيل والإعدادات، جلب من
السحابة أو رفع يدوي، متابعة المهام، تنزيل حزمة النتائج.

## الأدلة
- `engine/START_HERE.md` — ابدأ هنا.
- `engine/NEW_CASE_GUIDE.md` — تشغيل قضية جديدة خطوة بخطوة (`case_config.json`).
- `service/README_CLOUD_DRIVES.md` — تفعيل Google Drive / OneDrive / Azure OCR.
- `service/README_INTEGRATION.md` — تكامل الخدمة مع أي منصة (REST API).
- `engine/الكتيّب_الرسمي.md` — الكتيّب الجامع (فكرة النظام + الاستخدام + الخارطة).

## توليد واجهة التصفّح (العارض)
بعد معالجة قضية (`CASE_ROOT` يشير لمجلدها):
```bash
python scripts/make_viewer.py     # ينتج viewer/index.html — يعمل دون خادم
```
وفيها زر «☁ سحابة» للجلب المباشر من Google Drive / OneDrive عبر الخدمة.

> كل المخرجات مساعدة آلية تحتاج مراجعة محامٍ. المعالجة محلية بالكامل.
"""


def main():
    out_root = Path(sys.argv[1]) if len(sys.argv) > 1 else REPO / "dist"
    pkg = out_root / PKG_NAME
    if pkg.exists():
        shutil.rmtree(pkg)
    pkg.mkdir(parents=True)

    # 1) المحرّك ← engine/ (بالوثائق العامة، والنسخة العامة تحل محل كتيّب القضية)
    copy_tree(SRC_ENGINE, pkg / "engine")
    generic = pkg / "engine" / "الكتيّب_الرسمي_عام.md"
    if generic.exists():
        generic.rename(pkg / "engine" / "الكتيّب_الرسمي.md")

    # 2) الخدمة (بكل الإضافات: الربط السحابي، الواجهة، الإعدادات) + مولّد العارض
    copy_tree(REPO / "service", pkg / "service")
    for name in ("make_viewer.py", "make_project_pack.py"):
        src = REPO / "scripts" / name
        if src.exists():
            (pkg / "scripts").mkdir(exist_ok=True)
            (pkg / "scripts" / name).write_text(
                sanitize(src.read_text(encoding="utf-8")), encoding="utf-8")

    # 3) ملفات الجذر المفيدة (مُعقّمة)
    for name in (".env.example", "render.yaml", "try_azure.py",
                 "run_azure_test.sh", "run_azure_test.ps1",
                 "run_azure_reocr.sh", "run_azure_reocr.ps1"):
        src = REPO / name
        if src.exists():
            (pkg / name).write_text(sanitize(src.read_text(encoding="utf-8")),
                                    encoding="utf-8")
    (pkg / "README.md").write_text(GENERIC_README, encoding="utf-8")

    # 4) هياكل بيانات فارغة (قالب جاهز لأول قضية)
    for d in ("engine/outputs/json", "engine/outputs/csv", "engine/outputs/excel",
              "engine/outputs/word/documents", "engine/outputs/markdown",
              "engine/staging/text", "engine/staging/parts", "engine/staging/raw",
              "engine/staging/study"):
        (pkg / d).mkdir(parents=True, exist_ok=True)
        (pkg / d / ".gitkeep").write_text("", encoding="utf-8")

    # 5) الفحص النهائي: لا أثر لأي اسم/رقم/معرّف خاص
    hits = []
    for p in sorted(pkg.rglob("*")):
        if p.is_file() and is_text(p):
            body = p.read_text(encoding="utf-8", errors="replace")
            for w in BLOCKLIST:
                if w in body:
                    hits.append("%s ← %s" % (p.relative_to(pkg), w))
    if hits:
        print("✗ البناء فشل — بقايا بيانات خاصة:")
        for h in hits:
            print("  ", h)
        sys.exit(1)

    # 6) الضغط (أسماء عربية UTF-8)
    zpath = out_root / (PKG_NAME + "_clean.zip")
    with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED) as z:
        for p in sorted(pkg.rglob("*")):
            if p.is_file():
                zi = zipfile.ZipInfo(str(Path(PKG_NAME) / p.relative_to(pkg)))
                zi.flag_bits |= 0x800
                z.writestr(zi, p.read_bytes())
    n_files = sum(1 for p in pkg.rglob("*") if p.is_file())
    print("✓ الحزمة النظيفة جاهزة: %s (%d ملفاً)" % (zpath, n_files))
    print("✓ الفحص: لا أسماء ولا أرقام قضية ولا معرّفات خاصة.")


if __name__ == "__main__":
    main()
