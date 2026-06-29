# run_azure_reocr.ps1 — استكمال الحزمة عبر Azure (لا إعادة بناء).
# يختار الوثائق الضعيفة من الحزمة الحالية، يعيد OCR لها عبر Azure، يستبدل الأفضل فقط
# (يحفظ النص القديم)، ثم يعيد توليد الحزمة. لا يحتوي أي مفتاح ولا يرفع شيئاً إلى Git.
$ErrorActionPreference = "Stop"
Set-Location -Path $PSScriptRoot

$CASE = Join-Path $PSScriptRoot "zaini_case_audit_output"
$JSONL = Join-Path $CASE "outputs\json\full_documents.jsonl"
$BATCH = Join-Path $CASE "staging\reocr_batch"

Write-Host "=== 1) التحقق من Python ==="
$PY = $null
foreach ($c in @("python", "py")) {
    if (Get-Command $c -ErrorAction SilentlyContinue) { $PY = $c; break }
}
if (-not $PY) { Write-Host "X Python غير مثبّت."; exit 1 }
Write-Host ("OK " + (& $PY --version 2>&1))

Write-Host "=== 2) تثبيت المتطلبات (+ gdown للتنزيل من Drive) ==="
& $PY -m pip install -r service/requirements.txt
if ($LASTEXITCODE -ne 0) { Write-Host "X فشل تثبيت المتطلبات"; exit 1 }
& $PY -m pip install gdown | Out-Null

Write-Host "=== 3) التحقق من .env (Azure) ==="
if (-not (Test-Path ".env")) {
@"
ENGINE_MODE=azure
AZURE_DI_ENABLED=true
AZURE_DI_ENDPOINT=https://aman-legal-ocr.cognitiveservices.azure.com/
AZURE_DI_KEY=
AZURE_DI_MODEL=prebuilt-read
"@ | Set-Content -Encoding UTF8 ".env"
    Write-Host "! أُنشئ .env بدون مفتاح."
}
if (-not (Select-String -Path ".env" -Pattern '^AZURE_DI_KEY=.+' -Quiet)) {
    Write-Host "!! ضع KEY 1 في .env عند السطر AZURE_DI_KEY=... ثم أعد التشغيل."
    exit 1
}
Write-Host "OK AZURE_DI_KEY مضبوط"

Write-Host "=== 4) التحقق من بيانات الحزمة ==="
if (-not (Test-Path $JSONL)) {
    Write-Host "X لم يُعثر على بيانات الحزمة:"
    Write-Host "   $JSONL"
    Write-Host "   ضع ملف full_documents.jsonl (مصدر الحزمة) في هذا المسار أولاً."
    exit 1
}
Write-Host "OK full_documents.jsonl موجود"

# الحدّ الافتراضي للجولة: 5 وثائق (تجربة). غيّره بـ: $env:REOCR_MAX_DOCS = "0" لكل الضعيفة.
if (-not $env:REOCR_MAX_DOCS) { $env:REOCR_MAX_DOCS = "5" }
$thr = $env:REOCR_QUALITY_THRESHOLD; if (-not $thr) { $thr = "60" }
Write-Host ("حدّ الجولة (REOCR_MAX_DOCS) = " + $env:REOCR_MAX_DOCS + " | عتبة الجودة = " + $thr)

Write-Host "=== 5) تنزيل الوثائق الضعيفة من Google Drive ==="
& $PY zaini_case_audit_output/scripts/fetch_weak_docs.py
if ($LASTEXITCODE -ne 0) { Write-Host "X فشل التنزيل"; exit 1 }

Write-Host "=== 6) إعادة OCR انتقائية عبر Azure (استبدال الأفضل فقط، حفظ القديم) ==="
& $PY zaini_case_audit_output/scripts/reocr_generalize.py
if ($LASTEXITCODE -ne 0) { Write-Host "X فشلت إعادة OCR"; exit 1 }

Write-Host "=== 7) إعادة توليد الحزمة الوثائقية ==="
& $PY zaini_case_audit_output/scripts/legal_package.py

Write-Host ""
Write-Host "=== انتهى ==="
Write-Host "قرارات الاستبدال: zaini_case_audit_output\outputs\reocr_update\old_vs_new_comparison.csv"
Write-Host "سجل التعديلات:     zaini_case_audit_output\outputs\reocr_update\modifications_log.md"
Write-Host "النص القديم محفوظ في الحقل full_text_old داخل كل سجل. نسخة احتياطية في reocr_update\_backup\."
