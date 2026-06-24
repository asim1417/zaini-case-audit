# خدمة الفحص القانوني الآلي — حاوية متكاملة (محلية بالكامل)
FROM python:3.11-slim

# أدوات النظام: OCR عربي + Poppler (تحويل PDF لصور) + LibreOffice (تصدير PDF) + خطوط عربية حرة
RUN apt-get update && apt-get install -y --no-install-recommends \
    tesseract-ocr tesseract-ocr-ara \
    poppler-utils \
    libreoffice-writer \
    fonts-hosny-amiri fonts-kacst fonts-noto-core \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# المتطلبات أولاً (لاستغلال طبقات الكاش)
COPY service/requirements.txt /app/service/requirements.txt
RUN pip install --no-cache-dir -r /app/service/requirements.txt

# المحرّك + الخدمة
COPY zaini_case_audit_output/scripts /app/zaini_case_audit_output/scripts
COPY service /app/service

ENV JOBS_ROOT=/data/jobs
ENV PYTHONUNBUFFERED=1
RUN mkdir -p /data/jobs
VOLUME ["/data/jobs"]

EXPOSE 8080
WORKDIR /app/service
# عامل واحد افتراضاً (المعالجة ثقيلة)؛ زِد العمّال حسب موارد الخادم
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8080", "--workers", "1"]
