#!/usr/bin/env bash
# run_azure_test.sh — تشغيل ذاتي لتجربة Azure Document Intelligence على جهازك (Mac/Linux).
# لا يحتوي أي مفتاح. ضع KEY 1 في .env محلياً فقط. لا يرفع شيئاً إلى Git.
set -u
cd "$(dirname "$0")"

echo "=== 1) التحقق من Python ==="
if command -v python3 >/dev/null 2>&1; then PY=python3
elif command -v python >/dev/null 2>&1; then PY=python
else echo "✗ Python غير مثبّت. ثبّته من python.org ثم أعد المحاولة."; exit 1; fi
echo "✓ $($PY --version 2>&1)"

echo "=== 2) تثبيت المتطلبات ==="
$PY -m pip install -r service/requirements.txt || { echo "✗ فشل تثبيت المتطلبات"; exit 1; }

echo "=== 3) التحقق من .env ==="
if [ ! -f .env ]; then
  cat > .env <<'ENVF'
ENGINE_MODE=azure
AZURE_DI_ENABLED=true
AZURE_DI_ENDPOINT=https://aman-legal-ocr.cognitiveservices.azure.com/
AZURE_DI_KEY=
AZURE_DI_MODEL=prebuilt-read
ENVF
  echo "⚠ أُنشئ .env بدون مفتاح."
fi
# هل المفتاح مضبوط؟ (لا نطبع قيمته)
if grep -Eq '^AZURE_DI_KEY=.+' .env; then
  echo "✓ AZURE_DI_KEY مضبوط في .env"
else
  echo "‼ ضع KEY 1 في الملف .env عند السطر: AZURE_DI_KEY=..."
  echo "   افتح .env بمحرّر نصوص، الصق المفتاح، احفظ، ثم أعد تشغيل هذا السكربت."
  exit 1
fi

echo "=== 4) التحقق من document.pdf ==="
if [ ! -f document.pdf ]; then
  echo "‼ ضع ملف PDF غير سري باسم document.pdf في جذر المشروع، ثم أعد التشغيل."
  exit 1
fi
echo "✓ document.pdf موجود"

echo "=== 5) التشغيل ==="
$PY try_azure.py

echo
echo "=== 6) ملفات النتائج (في: $(pwd)) ==="
for f in azure_ocr_output.txt local_ocr_output.txt ocr_comparison_report.txt; do
  if [ -f "$f" ]; then echo "  ✓ $f"; else echo "  ✗ $f (لم يُنشأ)"; fi
done
echo "افتح ocr_comparison_report.txt لرؤية مقارنة الجودة بين Azure والمحلي."
