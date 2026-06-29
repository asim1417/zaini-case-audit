# رفع واجهة القضية على استضافة (قاعدة بيانات + حماية)

واجهة ويب خفيفة مرتبطة بقاعدة بيانات على الخادم: تعمل على الجوال والكمبيوتر،
وتُحمّل نتيجة بحث أو وثيقة واحدة عند الطلب (لا تُحمّل كل البيانات دفعة).

## المكوّنات
- `build_case_db.py` — يبني `case.db` (SQLite + بحث نصّي FTS5) من `full_documents.jsonl`.
- `case_server.py` — خادم FastAPI: دخول بكلمة مرور + واجهة + API.
- `start_case_server.sh` — يبني القاعدة إن لزم ثم يشغّل الخادم.

## ⚠️ الأمن أولاً (إلزامي)
- البيانات سرّية. **لا ترفع `full_documents.jsonl` ولا `case.db` إلى مستودع عام.**
  استخدم مستودعاً **خاصاً** أو ميزة «الملفات السرّية» في الاستضافة.
- اضبط `APP_PASSWORD` بكلمة قوية. لا يُعرض شيء قبل الدخول.
- يُفضّل استضافة لا تُفهرس (الرابط خاص). شارك الرابط وكلمة المرور بقناة آمنة.

## التشغيل محلياً (تجربة)
```bash
cd service
pip install -r requirements.txt
python build_case_db.py /path/to/full_documents.jsonl case.db
CASE_DB=case.db APP_PASSWORD=اختر_كلمة python -m uvicorn case_server:app --port 8080
# افتح http://localhost:8080
```

## الرفع على Render (مجاني للبداية)
1. أنشئ مستودعاً **خاصاً** فيه مجلد `service/` + ملف `full_documents.jsonl` بداخله.
2. Render → New → **Web Service** → اربط المستودع.
3. الإعدادات:
   - Runtime: Python 3
   - Build Command: `pip install -r service/requirements.txt`
   - Start Command: `bash service/start_case_server.sh`
   - Environment:
     - `APP_PASSWORD` = كلمة مرور قوية
     - `CASE_JSONL` = `service/full_documents.jsonl`
     - `CASE_DB` = `/tmp/case.db` (يُبنى عند الإقلاع)
4. بعد النشر: افتح الرابط → أدخل كلمة المرور.

## الرفع على Railway
- New Project → Deploy from repo (خاص) → Variables: `APP_PASSWORD`, `CASE_JSONL`, `CASE_DB`.
- Start Command: `bash service/start_case_server.sh`.

## المسارات (API)
- `GET /` دخول · `POST /login` · `GET /logout`
- `GET /app` الواجهة (بعد الدخول)
- `GET /api/list` · `GET /api/search?q=` · `GET /api/doc/{id}` · `GET /healthz`

## التحديث
عند تغيّر الوثائق: حدّث `full_documents.jsonl` واحذف `case.db` (يُعاد بناؤه)، أو أعد بناءه:
`python build_case_db.py full_documents.jsonl case.db`.
