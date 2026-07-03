#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
cloud_drives.py — ربط محرّك الفحص القانوني بـ Google Drive و OneDrive لجلب ملفات القضايا.

مزوّدان مدعومان:
  • Google Drive  (Drive API v3)      — مصادقة بحساب خدمة (موصى به) أو Refresh Token.
  • OneDrive      (Microsoft Graph)   — مصادقة تطبيق (Client Credentials) للمؤسسات،
                                        أو Device Code للحسابات الشخصية/المفوّضة.

يقبل رابط مشاركة أو معرّف مجلد/ملف، يستكشف المحتوى (تكرارياً للمجلدات الفرعية)،
ويحمّل الأنواع التي يدعمها المحرّك (PDF/JPG/PNG). مستندات Google الأصلية
(Docs/Sheets/Slides) تُصدَّر تلقائياً إلى PDF.

الاستخدام البرمجي:
    items = list_remote("google", "https://drive.google.com/drive/folders/XXXX")
    paths = fetch_to_dir("onedrive", "https://1drv.ms/f/s!Yyyy", Path("uploads"))

تسجيل دخول OneDrive بحساب شخصي/مفوّض (مرة واحدة، يحفظ التوكن):
    python cloud_drives.py login-onedrive
"""
import os, re, json, base64
from pathlib import Path

import requests

# الأنواع التي يقبلها المحرّك (pipeline.py يفحص PDF/JPEG/PNG بالتوقيع الثنائي)
SUPPORTED_EXTS = {".pdf", ".jpg", ".jpeg", ".png"}

# مستندات Google الأصلية → تُصدَّر PDF لتوافق المحرّك
GOOGLE_EXPORT_AS_PDF = {
    "application/vnd.google-apps.document",
    "application/vnd.google-apps.spreadsheet",
    "application/vnd.google-apps.presentation",
}
GOOGLE_FOLDER_MIME = "application/vnd.google-apps.folder"

CHUNK = 1024 * 256


class DriveError(RuntimeError):
    """خطأ ربط سحابي (إعداد ناقص، مصادقة، صلاحيات، رابط غير صالح)."""


def _safe_name(name: str, dest_dir: Path) -> Path:
    """اسم آمن داخل مجلد الوجهة، مع تفادي تصادم الأسماء."""
    name = Path(name).name or "file"
    dest = dest_dir / name
    i = 1
    while dest.exists():
        dest = dest_dir / ("%d_%s" % (i, name))
        i += 1
    return dest


# ══════════════════════════════ Google Drive ══════════════════════════════

class GoogleDrive:
    """عميل Google Drive API v3 للقراءة فقط.

    ترتيب المصادقة:
      1) حساب خدمة: GOOGLE_SERVICE_ACCOUNT_FILE (مسار JSON) أو
         GOOGLE_SERVICE_ACCOUNT_JSON (محتوى JSON مباشرة في المتغيّر).
         ⚠ شارِك المجلد في Drive مع بريد حساب الخدمة (…@…iam.gserviceaccount.com).
      2) OAuth شخصي: GOOGLE_OAUTH_CLIENT_ID + GOOGLE_OAUTH_CLIENT_SECRET +
         GOOGLE_OAUTH_REFRESH_TOKEN.
    """
    API = "https://www.googleapis.com/drive/v3"
    SCOPES = ["https://www.googleapis.com/auth/drive.readonly"]
    FIELDS = "id,name,mimeType,size,md5Checksum"

    def __init__(self):
        self.http = self._auth_session()

    def _auth_session(self):
        sa_json = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON", "").strip()
        sa_file = os.environ.get("GOOGLE_SERVICE_ACCOUNT_FILE", "").strip()
        cid = os.environ.get("GOOGLE_OAUTH_CLIENT_ID", "").strip()
        sec = os.environ.get("GOOGLE_OAUTH_CLIENT_SECRET", "").strip()
        ref = os.environ.get("GOOGLE_OAUTH_REFRESH_TOKEN", "").strip()
        if not (sa_json or sa_file or (cid and sec and ref)):
            raise DriveError(
                "Google Drive غير مهيأ: اضبط GOOGLE_SERVICE_ACCOUNT_FILE (أو _JSON)، "
                "أو ثلاثية GOOGLE_OAUTH_CLIENT_ID/SECRET/REFRESH_TOKEN.")
        try:
            from google.auth.transport.requests import AuthorizedSession
        except ImportError:
            raise DriveError("مكتبة google-auth غير مثبّتة: pip install google-auth requests")
        if sa_json or sa_file:
            from google.oauth2 import service_account
            info = json.loads(sa_json if sa_json else Path(sa_file).read_text(encoding="utf-8"))
            creds = service_account.Credentials.from_service_account_info(info, scopes=self.SCOPES)
            return AuthorizedSession(creds)
        from google.oauth2.credentials import Credentials
        creds = Credentials(None, refresh_token=ref, client_id=cid, client_secret=sec,
                            token_uri="https://oauth2.googleapis.com/token", scopes=self.SCOPES)
        return AuthorizedSession(creds)

    @staticmethod
    def extract_id(link_or_id: str) -> str:
        """يستخرج معرّف الملف/المجلد من رابط Drive بصيَغه الشائعة، أو يعيد المعرّف كما هو."""
        s = link_or_id.strip()
        for pat in (r"/folders/([A-Za-z0-9_-]{10,})", r"/d/([A-Za-z0-9_-]{10,})",
                    r"[?&]id=([A-Za-z0-9_-]{10,})"):
            m = re.search(pat, s)
            if m:
                return m.group(1)
        if re.fullmatch(r"[A-Za-z0-9_-]{10,}", s):
            return s
        raise DriveError("رابط/معرّف Google Drive غير صالح: %s" % s[:120])

    def _get(self, url, **params):
        r = self.http.get(url, params={**params, "supportsAllDrives": "true"}, timeout=120)
        if r.status_code == 404:
            raise DriveError("العنصر غير موجود أو لا صلاحية عليه (Google Drive). "
                             "تأكد من مشاركة المجلد مع بريد حساب الخدمة.")
        if r.status_code in (401, 403):
            raise DriveError("رُفضت مصادقة/صلاحية Google Drive (HTTP %d): %s"
                             % (r.status_code, r.text[:200]))
        r.raise_for_status()
        return r

    def metadata(self, file_id: str) -> dict:
        return self._get("%s/files/%s" % (self.API, file_id), fields=self.FIELDS).json()

    def list_files(self, link_or_id: str, recursive: bool = True) -> list:
        """قائمة الملفات القابلة للمعالجة تحت الرابط/المعرّف (ملف مفرد أو مجلد)."""
        root = self.metadata(self.extract_id(link_or_id))
        if root.get("mimeType") != GOOGLE_FOLDER_MIME:
            return [root] if self._processable(root) else []
        out, queue = [], [root["id"]]
        while queue:
            fid, token = queue.pop(0), None
            while True:
                r = self._get("%s/files" % self.API,
                              q="'%s' in parents and trashed=false" % fid,
                              fields="nextPageToken,files(%s)" % self.FIELDS,
                              pageSize=200, includeItemsFromAllDrives="true",
                              **({"pageToken": token} if token else {})).json()
                for it in r.get("files", []):
                    if it.get("mimeType") == GOOGLE_FOLDER_MIME:
                        if recursive:
                            queue.append(it["id"])
                    elif self._processable(it):
                        out.append(it)
                token = r.get("nextPageToken")
                if not token:
                    break
        return out

    @staticmethod
    def _processable(item: dict) -> bool:
        if item.get("mimeType") in GOOGLE_EXPORT_AS_PDF:
            return True
        return Path(item.get("name", "")).suffix.lower() in SUPPORTED_EXTS

    def download(self, item: dict, dest_dir: Path) -> Path:
        name, mime = item["name"], item.get("mimeType", "")
        if mime in GOOGLE_EXPORT_AS_PDF:
            url = "%s/files/%s/export" % (self.API, item["id"])
            params, name = {"mimeType": "application/pdf"}, Path(name).stem + ".pdf"
        else:
            url, params = "%s/files/%s" % (self.API, item["id"]), {"alt": "media"}
        dest = _safe_name(name, dest_dir)
        with self.http.get(url, params={**params, "supportsAllDrives": "true"},
                           stream=True, timeout=600) as r:
            r.raise_for_status()
            with dest.open("wb") as f:
                for chunk in r.iter_content(CHUNK):
                    f.write(chunk)
        return dest


# ═════════════════════════ OneDrive / Microsoft Graph ═════════════════════════

class OneDrive:
    """عميل OneDrive عبر Microsoft Graph API للقراءة فقط.

    ترتيب المصادقة:
      1) تطبيق مؤسسي (Client Credentials): MS_TENANT_ID + MS_CLIENT_ID + MS_CLIENT_SECRET
         مع صلاحية تطبيق Files.Read.All (بموافقة المسؤول). حدّد صاحب المساحة بـ
         MS_DRIVE_USER (بريد المستخدم) أو MS_DRIVE_ID.
      2) حساب شخصي/مفوّض (Device Code): MS_CLIENT_ID فقط، وسجّل مرة واحدة:
         python cloud_drives.py login-onedrive   (يحفظ التوكن في ONEDRIVE_TOKEN_CACHE)
    """
    GRAPH = "https://graph.microsoft.com/v1.0"
    DELEGATED_SCOPES = ["Files.Read.All"]

    def __init__(self):
        self.token = self._get_token()
        self.http = requests.Session()
        self.http.headers["Authorization"] = "Bearer " + self.token
        self._base = self._drive_base()

    # ---- المصادقة ----
    @staticmethod
    def _cache_path() -> Path:
        return Path(os.environ.get("ONEDRIVE_TOKEN_CACHE",
                                   str(Path.home() / ".onedrive_token_cache.json")))

    @classmethod
    def _msal(cls):
        try:
            import msal
        except ImportError:
            raise DriveError("مكتبة msal غير مثبّتة: pip install msal")
        return msal

    def _get_token(self) -> str:
        msal = self._msal()
        tenant = os.environ.get("MS_TENANT_ID", "").strip()
        cid = os.environ.get("MS_CLIENT_ID", "").strip()
        sec = os.environ.get("MS_CLIENT_SECRET", "").strip()
        if not cid:
            raise DriveError("OneDrive غير مهيأ: اضبط MS_CLIENT_ID (مع MS_TENANT_ID/"
                             "MS_CLIENT_SECRET للمؤسسات، أو login-onedrive للحساب الشخصي).")
        if tenant and sec:                        # تطبيق مؤسسي — بلا تدخل بشري
            app = msal.ConfidentialClientApplication(
                cid, client_credential=sec,
                authority="https://login.microsoftonline.com/" + tenant)
            res = app.acquire_token_for_client(scopes=["https://graph.microsoft.com/.default"])
        else:                                     # مفوّض — من ذاكرة توكن login-onedrive
            cache = msal.SerializableTokenCache()
            cp = self._cache_path()
            if cp.exists():
                cache.deserialize(cp.read_text(encoding="utf-8"))
            app = msal.PublicClientApplication(
                cid, authority="https://login.microsoftonline.com/common", token_cache=cache)
            accounts = app.get_accounts()
            res = (app.acquire_token_silent(self.DELEGATED_SCOPES, account=accounts[0])
                   if accounts else None)
            if res and cache.has_state_changed:
                cp.write_text(cache.serialize(), encoding="utf-8")
            if not res:
                raise DriveError("لا جلسة OneDrive محفوظة — نفّذ أولاً: "
                                 "python cloud_drives.py login-onedrive")
        if "access_token" not in (res or {}):
            raise DriveError("فشلت مصادقة Microsoft Graph: %s"
                             % (res or {}).get("error_description", res))
        return res["access_token"]

    def _drive_base(self) -> str:
        """جذر مساحة التخزين: /me للمفوّض، أو مستخدم/معرّف محدّد للتطبيق المؤسسي."""
        drive_id = os.environ.get("MS_DRIVE_ID", "").strip()
        user = os.environ.get("MS_DRIVE_USER", "").strip()
        if drive_id:
            return "%s/drives/%s" % (self.GRAPH, drive_id)
        if user:
            return "%s/users/%s/drive" % (self.GRAPH, user)
        if os.environ.get("MS_CLIENT_SECRET", "").strip():
            raise DriveError("مع مصادقة التطبيق المؤسسي حدّد MS_DRIVE_USER "
                             "(بريد صاحب OneDrive) أو MS_DRIVE_ID.")
        return "%s/me/drive" % self.GRAPH

    # ---- الوصول للعناصر ----
    def _get(self, url, **params):
        r = self.http.get(url, params=params or None, timeout=120)
        if r.status_code == 404:
            raise DriveError("العنصر غير موجود أو لا صلاحية عليه (OneDrive/Graph).")
        if r.status_code in (401, 403):
            raise DriveError("رُفضت مصادقة/صلاحية Microsoft Graph (HTTP %d): %s"
                             % (r.status_code, r.text[:200]))
        r.raise_for_status()
        return r

    @staticmethod
    def _share_token(url: str) -> str:
        """ترميز رابط مشاركة إلى معرّف shares حسب توثيق Graph (u!base64url)."""
        return "u!" + base64.urlsafe_b64encode(url.encode("utf-8")).decode().rstrip("=")

    def resolve(self, link_or_id: str) -> dict:
        """يحوّل رابط مشاركة / مسار / معرّف عنصر إلى driveItem."""
        s = link_or_id.strip()
        if s.lower().startswith(("http://", "https://")):
            return self._get("%s/shares/%s/driveItem" % (self.GRAPH, self._share_token(s))).json()
        if s.startswith("/"):                                     # مسار داخل المساحة
            return self._get("%s/root:%s:" % (self._base, s.rstrip("/"))).json()
        return self._get("%s/items/%s" % (self._base, s)).json()  # معرّف عنصر

    def _children_url(self, item: dict) -> str:
        # عنصر من رابط مشاركة قد يقيم في مساحة مختلفة → استخدم drive الخاص به
        drive_id = (item.get("parentReference") or {}).get("driveId", "")
        base = "%s/drives/%s" % (self.GRAPH, drive_id) if drive_id else self._base
        return "%s/items/%s/children" % (base, item["id"])

    def list_files(self, link_or_id: str, recursive: bool = True) -> list:
        root = self.resolve(link_or_id)
        if "folder" not in root:
            return [root] if self._processable(root) else []
        out, queue = [], [root]
        while queue:
            folder = queue.pop(0)
            url = self._children_url(folder) + "?$top=200"
            while url:
                page = self._get(url).json()
                for it in page.get("value", []):
                    if "folder" in it:
                        if recursive:
                            queue.append(it)
                    elif self._processable(it):
                        out.append(it)
                url = page.get("@odata.nextLink", "")
        return out

    @staticmethod
    def _processable(item: dict) -> bool:
        return Path(item.get("name", "")).suffix.lower() in SUPPORTED_EXTS

    def download(self, item: dict, dest_dir: Path) -> Path:
        dest = _safe_name(item["name"], dest_dir)
        url = item.get("@microsoft.graph.downloadUrl")
        if url:                                   # رابط مؤقت مُصادَق مسبقاً
            r = requests.get(url, stream=True, timeout=600)
        else:
            drive_id = (item.get("parentReference") or {}).get("driveId", "")
            base = "%s/drives/%s" % (self.GRAPH, drive_id) if drive_id else self._base
            r = self.http.get("%s/items/%s/content" % (base, item["id"]),
                              stream=True, timeout=600)
        with r:
            r.raise_for_status()
            with dest.open("wb") as f:
                for chunk in r.iter_content(CHUNK):
                    f.write(chunk)
        return dest


# ══════════════════════════════ واجهة موحّدة ══════════════════════════════

PROVIDERS = {"google": GoogleDrive, "gdrive": GoogleDrive, "google_drive": GoogleDrive,
             "onedrive": OneDrive, "microsoft": OneDrive, "ms": OneDrive}


def providers_status() -> dict:
    """حالة تهيئة كل مزوّد (من متغيّرات البيئة) — تستهلكها الواجهة لعرض شارات التفعيل."""
    g_mode = ""
    if (os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON", "").strip()
            or os.environ.get("GOOGLE_SERVICE_ACCOUNT_FILE", "").strip()):
        g_mode = "service_account"
    elif all(os.environ.get(k, "").strip() for k in
             ("GOOGLE_OAUTH_CLIENT_ID", "GOOGLE_OAUTH_CLIENT_SECRET", "GOOGLE_OAUTH_REFRESH_TOKEN")):
        g_mode = "oauth_refresh_token"
    o_mode = ""
    if os.environ.get("MS_CLIENT_ID", "").strip():
        if (os.environ.get("MS_TENANT_ID", "").strip()
                and os.environ.get("MS_CLIENT_SECRET", "").strip()):
            o_mode = "client_credentials"
        elif OneDrive._cache_path().exists():
            o_mode = "device_code"
    return {"google": {"configured": bool(g_mode), "mode": g_mode},
            "onedrive": {"configured": bool(o_mode), "mode": o_mode}}


def _client(provider: str):
    cls = PROVIDERS.get((provider or "").strip().lower())
    if not cls:
        raise DriveError("مزوّد غير مدعوم: %r (المدعوم: google | onedrive)" % provider)
    return cls()


def list_remote(provider: str, link_or_id: str, recursive: bool = True) -> list:
    """معاينة الملفات القابلة للمعالجة دون تنزيل. يعيد [{name,size,mime,id}]."""
    items = _client(provider).list_files(link_or_id, recursive)
    return [{"id": it.get("id", ""), "name": it.get("name", ""),
             "size": int(it.get("size", 0) or 0),
             "mime": it.get("mimeType", (it.get("file") or {}).get("mimeType", ""))}
            for it in items]


def fetch_to_dir(provider: str, link_or_id: str, dest_dir: Path,
                 recursive: bool = True, max_files: int = 500, log=print) -> list:
    """يحمّل ملفات الرابط إلى dest_dir ويعيد قائمة المسارات المحلية."""
    dest_dir = Path(dest_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)
    client = _client(provider)
    items = client.list_files(link_or_id, recursive)
    if not items:
        raise DriveError("لا ملفات قابلة للمعالجة (PDF/JPG/PNG) تحت هذا الرابط.")
    if len(items) > max_files:
        raise DriveError("عدد الملفات (%d) يتجاوز الحدّ (%d)." % (len(items), max_files))
    paths = []
    for i, it in enumerate(items, 1):
        p = client.download(it, dest_dir)
        paths.append(p)
        log("تنزيل [%d/%d] %s (%.1f KB)" % (i, len(items), p.name, p.stat().st_size / 1024))
    return paths


# ══════════════════ أداة سطر أوامر: تسجيل دخول OneDrive ══════════════════

def _login_onedrive():
    """تدفّق Device Code: يعرض رمزاً تُدخله في microsoft.com/devicelogin ثم يحفظ التوكن."""
    msal = OneDrive._msal()
    cid = os.environ.get("MS_CLIENT_ID", "").strip()
    if not cid:
        raise SystemExit("اضبط MS_CLIENT_ID أولاً (معرّف تطبيق مسجّل في Azure/Entra).")
    cache = msal.SerializableTokenCache()
    cp = OneDrive._cache_path()
    if cp.exists():
        cache.deserialize(cp.read_text(encoding="utf-8"))
    app = msal.PublicClientApplication(
        cid, authority="https://login.microsoftonline.com/common", token_cache=cache)
    flow = app.initiate_device_flow(scopes=OneDrive.DELEGATED_SCOPES)
    if "user_code" not in flow:
        raise SystemExit("تعذّر بدء Device Flow: %s" % flow.get("error_description", flow))
    print(flow["message"])                        # افتح الرابط وأدخل الرمز
    res = app.acquire_token_by_device_flow(flow)
    if "access_token" not in res:
        raise SystemExit("فشل تسجيل الدخول: %s" % res.get("error_description", res))
    cp.write_text(cache.serialize(), encoding="utf-8")
    print("تم تسجيل الدخول وحفظ الجلسة في: %s" % cp)


if __name__ == "__main__":
    import sys
    if sys.argv[1:2] == ["login-onedrive"]:
        _login_onedrive()
    elif len(sys.argv) >= 4 and sys.argv[1] in ("list", "fetch"):
        # اختبار سريع: python cloud_drives.py list google <رابط>
        #              python cloud_drives.py fetch onedrive <رابط> [مجلد الوجهة]
        cmd, prov, link = sys.argv[1], sys.argv[2], sys.argv[3]
        if cmd == "list":
            for it in list_remote(prov, link):
                print("%10d  %-60s %s" % (it["size"], it["name"], it["mime"]))
        else:
            dest = Path(sys.argv[4]) if len(sys.argv) > 4 else Path("./drive_downloads")
            for p in fetch_to_dir(prov, link, dest):
                print(p)
    else:
        print(__doc__)
