#!/usr/bin/env bash
# run_azure_reocr.sh — استكمال الحزمة عبر Azure (لا إعادة بناء) — Mac/Linux.
# يختار الوثائق الضعيفة من الحزمة الحالية، يعيد OCR لها عبر Azure، يستبدل الأفضل فقط
# (يحفظ النص القديم)، ثم يعيد توليد الحزمة. لا يحتوي أي مفتاح ولا يرفع شيئاً إلى Git.
set -u
cd "$(dirname "$0")"

CASE="zaini_case_audit_output"
JSONL="$CASE/outputs/json/full_documents.jsonl"
BATCH="$CASE/staging/reocr_batch"

echo "=== 1) التحقق من Python ==="
if command -v python3 >/dev/null 2>&1; then PY=python3
elif command -v python >/dev/null 2>&1; then PY=python
else echo "✗ Python غير مثبّت."; exit 1; fi
echo "✓ $($PY --version 2>&1)"

echo "=== 2) تثبيت المتطلبات ==="
$PY -m pip install -r service/requirements.txt || { echo "✗ فشل تثبيت المتطلبات"; exit 1; }

echo "=== 3) التحقق من .env (Azure) ==="
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
if ! grep -Eq '^AZURE_DI_KEY=.+' .env; then
  echo "‼ ضع KEY 1 في .env عند السطر AZURE_DI_KEY=... ثم أعد التشغيل."
  exit 1
fi
echo "✓ AZURE_DI_KEY مضبوط"

echo "=== 4) التحقق من بيانات الحزمة ==="
if [ ! -f "$JSONL" ]; then
  echo "✗ لم يُعثر على بيانات الحزمة: $JSONL"
  echo "   ضع ملف full_documents.jsonl (مصدر الحزمة) في هذا المسار أولاً."
  exit 1
fi
echo "✓ full_documents.jsonl موجود"
if [ ! -d "$BATCH" ]; then
  echo "‼ تنبيه: مجلد ملفات المصدر غير موجود: $BATCH"
  echo "   ضع ملفات PDF/صور الوثائق الضعيفة هناك باسم <fileId>.pdf؛"
  echo "   الوثائق بلا مصدر ستُبقى كما هي (لن تُعاد OCR)."
fi

echo "=== 5) إعادة OCR انتقائية عبر Azure (استبدال الأفضل فقط، حفظ القديم) ==="
# لضبط العتبة وحدّ عدد الوثائق لكل جولة (مفيد لباقة F0):
#   export REOCR_QUALITY_THRESHOLD=60
#   export REOCR_MAX_DOCS=5
$PY zaini_case_audit_output/scripts/reocr_generalize.py || { echo "✗ فشلت إعادة OCR"; exit 1; }

echo "=== 6) إعادة توليد الحزمة الوثائقية ==="
$PY zaini_case_audit_output/scripts/legal_package.py

echo
echo "=== انتهى ==="
echo "قرارات الاستبدال: $CASE/outputs/reocr_update/old_vs_new_comparison.csv"
echo "سجل التعديلات:     $CASE/outputs/reocr_update/modifications_log.md"
echo "النص القديم محفوظ في الحقل full_text_old داخل كل سجل. نسخة احتياطية في reocr_update/_backup/."
