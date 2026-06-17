# تعليمات جاهزة لوكيل الذكاء الاصطناعي (انسخها والصقها)

استخدم هذا النص مع وكيل برمجي يستطيع تنفيذ الأوامر (مثل Claude Code)، بعد أن ترفع له
«عدّة الأداة» المضغوطة. الصق ما يلي:

---

أنت مساعد تقني. لديك عدّة أداة لفحص مستندات القضايا القانونية (مجلد scripts فيه
سكربتات بايثون + Dockerfile + requirements.txt). نفّذ التالي بدقّة:

1) ثبّت المتطلبات:
   - أدوات النظام: tesseract-ocr و tesseract-ocr-ara و poppler-utils و unrar و p7zip-full.
   - مكتبات بايثون: `pip install -r requirements.txt`.
   (أو ابنِ صورة Docker: `docker build -t legal-audit .`)

2) أنشئ قضية جديدة:
   `python3 scripts/legal_audit.py new قضيتي`

3) جهّز المستندات داخل `cases/قضيتي/staging/`:
   - لكل مستند: ضع نصّه في `staging/text/<معرّف>.txt`.
   - وأضف سطر JSON لكل مستند في `staging/parts/docs.jsonl` بالحقول:
     {"id","title","mimeType","fileExtension","fileSize","createdTime","modifiedTime",
      "viewUrl","owner","parentId","parent_path","is_folder":false,"text_chars",
      "text_file","read_status":"ok","read_error":null}
   - (اختياري) أرشيفات/صور خام في `staging/raw/` لمعالجتها لاحقاً.

4) عدّل `cases/قضيتي/case_config.json` بمعطيات القضية (رقم القضية، الأطراف،
   أرقام الصكوك، اسم الشركة/الجهة).

5) شغّل الفحص الكامل:
   `python3 scripts/legal_audit.py run قضيتي`

6) سلّمني المخرجات من `cases/قضيتي/outputs/` و`cases/قضيتي/zaini_outputs_bundle.zip`:
   ابدأ بالفهرس `outputs/excel/00_master_documents.xlsx` والموجز
   `outputs/word/00_ملخص_القضية.docx`.

قيود إلزامية: لا تُرسل بيانات القضية لأي خدمة خارجية (المعالجة محلية)، وكل المخرجات
«مساعدة آلية تحتاج مراجعة المحامي» وليست رأياً قانونياً نهائياً.

---
