# run_azure_test.ps1 — تشغيل ذاتي لتجربة Azure Document Intelligence على Windows.
# لا يحتوي أي مفتاح. ضع KEY 1 في .env محلياً فقط. لا يرفع شيئاً إلى Git.
$ErrorActionPreference = "Stop"
Set-Location -Path $PSScriptRoot

Write-Host "=== 1) التحقق من Python ==="
$PY = $null
foreach ($c in @("python", "py")) {
    if (Get-Command $c -ErrorAction SilentlyContinue) { $PY = $c; break }
}
if (-not $PY) { Write-Host "X Python غير مثبّت. ثبّته من python.org ثم أعد المحاولة."; exit 1 }
Write-Host ("OK " + (& $PY --version 2>&1))

Write-Host "=== 2) تثبيت المتطلبات ==="
& $PY -m pip install -r service/requirements.txt
if ($LASTEXITCODE -ne 0) { Write-Host "X فشل تثبيت المتطلبات"; exit 1 }

Write-Host "=== 3) التحقق من .env ==="
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
# هل المفتاح مضبوط؟ (لا نطبع قيمته)
$hasKey = Select-String -Path ".env" -Pattern '^AZURE_DI_KEY=.+' -Quiet
if ($hasKey) {
    Write-Host "OK AZURE_DI_KEY مضبوط في .env"
} else {
    Write-Host "!! ضع KEY 1 في الملف .env عند السطر: AZURE_DI_KEY=..."
    Write-Host "   افتح .env بمحرّر نصوص، الصق المفتاح، احفظ، ثم أعد تشغيل هذا السكربت."
    exit 1
}

Write-Host "=== 4) التحقق من document.pdf ==="
if (-not (Test-Path "document.pdf")) {
    Write-Host "!! ضع ملف PDF غير سري باسم document.pdf في جذر المشروع، ثم أعد التشغيل."
    exit 1
}
Write-Host "OK document.pdf موجود"

Write-Host "=== 5) التشغيل ==="
& $PY try_azure.py

Write-Host ""
Write-Host ("=== 6) ملفات النتائج (في: " + (Get-Location) + ") ===")
foreach ($f in @("azure_ocr_output.txt", "local_ocr_output.txt", "ocr_comparison_report.txt")) {
    if (Test-Path $f) { Write-Host ("  OK " + $f) } else { Write-Host ("  X " + $f + " (لم يُنشأ)") }
}
Write-Host "افتح ocr_comparison_report.txt لرؤية مقارنة الجودة بين Azure والمحلي."
