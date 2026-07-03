# أداة معالجة الوثائق العربية — دليل النشر على خادم «حكيم»

أداة **عامة قابلة للتداول**: يرفع المستخدم وثائقه (نص / Word / PDF / صور) فتُستخرَج
وتُنظَّف (تطبيع عربي: إزالة علامات الاتجاه، توحيد الحروف الفارسية الشبيهة، تحويل الأرقام
الفارسية) وتُفهرَس للبحث الفوري وتُعرَض مع تظليل مواضع المطابقة.

> **لا تحتوي الأداة أي بيانات قضية.** كل وثيقة يعالجها المستخدم تُخزَّن في قاعدة بيانات
> محلية على خادمك فقط. آمنة للنشر والمشاركة.

الملف: `service/tool_app.py` — تطبيق FastAPI بملف واحد، بلا اعتماد على أي ملف بيانات.

---

## 1) التشغيل محلياً (تجربة سريعة)

```bash
cd service
python3 -m pip install -r requirements_tool.txt
uvicorn tool_app:app --host 0.0.0.0 --port 8080
```

ثم افتح: `http://localhost:8080`

## 2) قفل الأداة بكلمة مرور (اختياري لكن مُوصى به للنشر العام)

```bash
export APP_PASSWORD="اختر-كلمة-مرور-قوية"
export SESSION_SECRET="سلسلة-عشوائية-طويلة"     # اختياري: لتوقيع الجلسة
uvicorn tool_app:app --host 0.0.0.0 --port 8080
```

بدون `APP_PASSWORD` تكون الأداة مفتوحة للجميع (مناسب خلف شبكة داخلية فقط).

## 3) النشر على خادم «حكيم» (خادم Python تملكه)

### أ. تشغيل دائم عبر systemd (مُستحسَن)
أنشئ `/etc/systemd/system/hakeem-tool.service`:

```ini
[Unit]
Description=Arabic Documents Tool
After=network.target

[Service]
WorkingDirectory=/opt/hakeem/service
Environment=APP_PASSWORD=ضع-كلمة-المرور
Environment=TOOL_DB=/opt/hakeem/data/tool_docs.db
ExecStart=/usr/bin/uvicorn tool_app:app --host 127.0.0.1 --port 8080
Restart=always

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload && sudo systemctl enable --now hakeem-tool
```

### ب. الواجهة الخلفية عبر Nginx (HTTPS + نطاقك)
```nginx
location /tool/ {
    proxy_pass http://127.0.0.1:8080/;
    proxy_set_header Host $host;
    client_max_body_size 50M;      # للسماح برفع ملفات كبيرة
}
```

## 4) تفعيل OCR للـPDF الممسوح والصور (اختياري)
```bash
sudo apt-get install -y tesseract-ocr tesseract-ocr-ara poppler-utils
python3 -m pip install pytesseract pdf2image Pillow
```
بدونها: النص و‏Word و‏PDF النصّي تعمل؛ الصور والـPDF الممسوح تُقبل لكن دون استخراج.

## 5) الصيغ المدعومة
| الصيغة | الاستخراج | يحتاج |
|---|---|---|
| `.txt .md .csv .json` | مباشر | — |
| `.docx` | python-docx | أساسي |
| `.pdf` (نصّي) | pdfminer.six | أساسي |
| `.pdf` (ممسوح) | OCR | tesseract + poppler |
| `.png .jpg .tif …` | OCR | tesseract + Pillow |

## 6) نقاط الوصول (API)
- `GET  /` — الواجهة (رفع + بحث + عرض)
- `POST /api/upload` — رفع ملفات (multipart) → استخراج + فهرسة
- `GET  /api/docs` — قائمة الوثائق
- `GET  /api/search?q=` — بحث FTS مع مقتطفات
- `GET  /api/doc/{id}` — وثيقة كاملة
- `POST /api/clear` — مسح كل الوثائق
- `GET  /healthz` — فحص الحالة

## 7) ملاحظات
- قاعدة البيانات في `TOOL_DB` (افتراضياً في مجلد مؤقت). حدِّد مساراً دائماً عند النشر.
- الرفع والبحث يعملان بلا اتصال خارجي؛ لا تُرسَل بيانات لأي خدمة.
- لإعادة الضبط من الصفر: احذف ملف `TOOL_DB`.
