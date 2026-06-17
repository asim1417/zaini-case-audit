# صورة تشغيل نظام الفحص القانوني — تثبيت بأمر واحد
# البناء:   docker build -t legal-audit .
# التشغيل:  docker run --rm -v "$PWD/zaini_case_audit_output:/app" legal-audit bash scripts/run_all.sh
#
# الصورة تثبّت كل أدوات النظام (OCR عربي، فكّ ضغط) + مكتبات بايثون،
# لتعمل المعالجة محلياً بالكامل دون إرسال بيانات القضية لأي خدمة خارجية.
FROM python:3.11-slim

# أدوات النظام: OCR (مع العربية)، تحويل PDF لصور، فكّ ضغط rar/7z
RUN apt-get update && apt-get install -y --no-install-recommends \
        tesseract-ocr \
        tesseract-ocr-ara \
        poppler-utils \
        unrar-free \
        p7zip-full \
        fonts-arabeyes \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

# يُتوقّع تركيب مجلد المخرجات (فيه scripts/ و staging/) عند التشغيل عبر -v
CMD ["bash", "scripts/run_all.sh"]
