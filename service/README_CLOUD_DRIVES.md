# الربط مع Google Drive و OneDrive — جلب ملفات القضايا مباشرة

هذه الوحدة (`service/cloud_drives.py`) تربط محرّك زيني بمساحات التخزين السحابية،
فبدل رفع الملفات يدوياً إلى `POST /jobs`، ترسل **رابط مشاركة** أو **معرّف مجلد**
وتتكفل الخدمة بجلب كل الملفات القابلة للمعالجة (PDF / JPG / PNG) — بما فيها
المجلدات الفرعية — ثم تمرّرها لخط المعالجة الاعتيادي (OCR → فهرسة → حزمة).

> مستندات Google الأصلية (Docs / Sheets / Slides) تُصدَّر تلقائياً إلى PDF.

## المكتبات المطلوبة

مضافة في `service/requirements.txt` (تُثبَّت تلقائياً مع Docker):

```
pip install requests google-auth msal
```

| المكتبة | الغرض |
|---|---|
| `google-auth` | مصادقة Google (حساب خدمة أو Refresh Token) — نستدعي Drive API v3 عبر REST مباشرة |
| `msal` | مصادقة Microsoft (Entra ID) — نستدعي Microsoft Graph عبر REST مباشرة |
| `requests` | نقل HTTP وتنزيل الملفات تدفقياً |

---

## أولاً: إعداد Google Drive

### الخيار 1 — حساب خدمة (موصى به للخوادم، بلا تدخل بشري)

1. افتح [Google Cloud Console](https://console.cloud.google.com) → أنشئ مشروعاً (أو استخدم موجوداً).
2. **APIs & Services → Library** → فعّل **Google Drive API**.
3. **APIs & Services → Credentials → Create Credentials → Service Account**
   → بعد الإنشاء: **Keys → Add Key → JSON** ونزّل الملف.
4. في Google Drive، **شارِك مجلد القضايا** مع بريد حساب الخدمة
   (يشبه `name@project.iam.gserviceaccount.com`) بصلاحية *Viewer*.
5. اضبط أحد المتغيّرين:

```bash
GOOGLE_SERVICE_ACCOUNT_FILE=/path/to/service-account.json
# أو ألصق المحتوى مباشرة (مناسب لأسرار Render/Docker):
GOOGLE_SERVICE_ACCOUNT_JSON='{"type":"service_account", ...}'
```

### الخيار 2 — حساب شخصي (OAuth Refresh Token)

1. في نفس المشروع: **Credentials → Create Credentials → OAuth client ID** (نوع *Web application*)
   وأضف `https://developers.google.com/oauthplayground` كـ Redirect URI.
2. افتح [OAuth Playground](https://developers.google.com/oauthplayground) → ⚙ →
   فعّل *Use your own OAuth credentials* وألصق المعرّف والسر.
3. في الخطوة 1 اختر النطاق `https://www.googleapis.com/auth/drive.readonly` → Authorize.
4. في الخطوة 2 اضغط *Exchange authorization code for tokens* وانسخ **Refresh Token**.

```bash
GOOGLE_OAUTH_CLIENT_ID=xxxx.apps.googleusercontent.com
GOOGLE_OAUTH_CLIENT_SECRET=xxxx
GOOGLE_OAUTH_REFRESH_TOKEN=xxxx
```

---

## ثانياً: إعداد OneDrive (Microsoft Graph)

سجّل تطبيقاً في [Azure Portal](https://portal.azure.com) → **Microsoft Entra ID → App registrations → New registration**:
- *Supported account types*: للمؤسسة فقط، أو "Personal Microsoft accounts" إن كان OneDrive شخصياً.

### الخيار 1 — مؤسسي (Client Credentials، بلا تدخل بشري)

1. **API permissions → Add → Microsoft Graph → Application permissions → `Files.Read.All`**
   → اضغط **Grant admin consent**.
2. **Certificates & secrets → New client secret** وانسخ القيمة.
3. اضبط:

```bash
MS_TENANT_ID=معرّف-المستأجر
MS_CLIENT_ID=معرّف-التطبيق
MS_CLIENT_SECRET=السر
MS_DRIVE_USER=owner@company.com     # صاحب مساحة OneDrive المستهدفة (أو MS_DRIVE_ID)
```

### الخيار 2 — حساب شخصي/مفوّض (Device Code، تسجيل مرة واحدة)

1. في التطبيق المسجّل: **Authentication → Advanced settings → Allow public client flows = Yes**.
2. **API permissions → Delegated permissions → `Files.Read.All`**.
3. على الخادم:

```bash
export MS_CLIENT_ID=معرّف-التطبيق
python service/cloud_drives.py login-onedrive
# يعرض رمزاً → افتح https://microsoft.com/devicelogin وأدخله وسجّل الدخول
# تُحفظ الجلسة في ~/.onedrive_token_cache.json (أو ONEDRIVE_TOKEN_CACHE)
```

---

## ثالثاً: الاستخدام من واجهة العارض (زر «☁ سحابة»)

واجهة تصفّح القضية (المولّدة بـ `scripts/make_viewer.py`) فيها زر **«☁ سحابة»** في شريط
الأدوات العلوي:

1. شغّل خدمة المعالجة (Docker أو Render) بعد ضبط متغيّرات المصادقة أدناه — **التفعيل
   يتم مرة واحدة على الخادم**؛ العارض ملف ثابت لا يحمل أسراراً.
2. افتح العارض → «☁ سحابة» → أدخل عنوان الخدمة (يُحفظ في المتصفّح) ومفتاح API إن وُجد.
3. اختر المزوّد وألصق رابط المشاركة → «معاينة الملفات» ثم «جلب ومعالجة».
4. عند اكتمال المعالجة تُحمَّل الوثائق الجديدة **مباشرة داخل العارض** — مدموجة مع
   وثائق القضية الحالية (الافتراضي) أو كقضية جديدة.

> تقنياً: العارض يستدعي `POST /jobs/from-drive` ثم يتابع الحالة ثم يجلب
> `GET /jobs/{id}/case_data` (نتائج المهمّة بصيغة `window.CASE`). لذلك يجب أن يكون
> `CORS_ORIGINS` في الخدمة يسمح بأصل العارض (الافتراضي `*`).

كما تتوفر واجهة ويب مدمجة في الخدمة نفسها على `GET /` (جلب سحابي + رفع يدوي +
متابعة المهام + تنزيل الحزمة).

## رابعاً: الاستخدام عبر API

### معاينة الملفات قبل الجلب (للواجهة)

```bash
curl -s -X POST http://HOST:8080/drive/list \
  -H "Content-Type: application/json" \
  -d '{"provider":"google","link":"https://drive.google.com/drive/folders/1AbC..."}'
# → {"count": 42, "files": [{"id":"...","name":"حكم.pdf","size":183021,"mime":"application/pdf"}, ...]}
```

### إنشاء مهمّة من رابط سحابي

```bash
curl -s -X POST "http://HOST:8080/jobs/from-drive?x_api_key=$KEY" \
  -H "Content-Type: application/json" \
  -d '{"provider":"onedrive","link":"https://1drv.ms/f/s!AbCdEf...","recursive":true}'
# → {"job_id":"ab12cd34ef56","status":"downloading"}
```

بعدها المتابعة كالمعتاد: `GET /jobs/{job_id}` (الحالات: `downloading → running → done`)
ثم `GET /jobs/{job_id}/result` لتنزيل الحزمة.

يقبل حقل `link`:
- **Google**: رابط مجلد (`…/drive/folders/ID`)، رابط ملف (`…/d/ID/…`)، أو المعرّف مباشرة.
- **OneDrive**: رابط مشاركة (`1drv.ms` أو `sharepoint.com`)، مسار داخل المساحة
  (`/قضايا/الزيني`)، أو معرّف عنصر.

### الاستخدام البرمجي المباشر (بايثون)

```python
from pathlib import Path
import cloud_drives

# معاينة
files = cloud_drives.list_remote("google", "https://drive.google.com/drive/folders/1AbC...")

# تنزيل إلى مجلد ثم تشغيل المحرّك عليه
paths = cloud_drives.fetch_to_dir("onedrive", "https://1drv.ms/f/s!AbC...", Path("uploads"))
```

### اختبار سريع من سطر الأوامر

```bash
python service/cloud_drives.py list  google   "https://drive.google.com/drive/folders/1AbC..."
python service/cloud_drives.py fetch onedrive "https://1drv.ms/f/s!AbC..." ./downloads
```

---

## ملاحظات أمنية

- الصلاحيات **قراءة فقط** (`drive.readonly` / `Files.Read.All`) — الخدمة لا تعدّل ولا تحذف شيئاً في السحابة.
- الأسرار كلها عبر متغيّرات البيئة؛ لا تُودِع ملفات المفاتيح في المستودع.
- بعد التنزيل تجري كل المعالجة محلياً كالمعتاد؛ لا تُرسل النصوص لأي طرف خارجي.
- `MAX_FILES` (افتراضياً 500) يحدّ عدد الملفات المجلوبة لكل مهمّة.
