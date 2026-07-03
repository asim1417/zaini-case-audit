#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
app.py — خدمة REST API لمحرّك الفحص القانوني (FastAPI).

نمط مهام غير متزامن: ارفع الملفات → احصل على job_id → تابع الحالة → نزّل الحزمة.
كل المعالجة محلية على خادمكم؛ لا تخرج البيانات لأي خدمة خارجية.

جلب سحابي (اختياري): POST /jobs/from-drive يجلب الملفات مباشرة من
Google Drive أو OneDrive عبر رابط مشاركة/معرّف مجلد — انظر cloud_drives.py
و README_CLOUD_DRIVES.md لتهيئة المصادقة.

التشغيل المحلي:  uvicorn app:app --host 0.0.0.0 --port 8080
التوثيق التفاعلي: GET /docs   (OpenAPI/Swagger يولّده FastAPI تلقائياً)
"""
import os, sys, io, csv, json, uuid, shutil, threading, datetime
from pathlib import Path

import re

from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from pydantic import BaseModel

import pipeline
import cloud_drives

# مولّد العارض (لتحويل نتائج مهمّة إلى صيغة واجهة التصفّح window.CASE)
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

JOBS_ROOT = Path(os.environ.get("JOBS_ROOT", "/data/jobs"))
JOBS_ROOT.mkdir(parents=True, exist_ok=True)
API_KEY = os.environ.get("API_KEY", "")          # إن ضُبط، يلزم تمريره بترويسة X-API-Key
MAX_FILES = int(os.environ.get("MAX_FILES", "500"))

# ─── إعدادات دائمة قابلة للضبط من الواجهة (تُحفظ في حجم البيانات وتُطبَّق على البيئة) ───
SETTINGS_FILE = JOBS_ROOT / "settings.json"
SETTINGS_KEYS = (
    # OCR سحابي اختياري (Azure Document Intelligence) — يقرأ البيئة وقت التنفيذ
    "ENGINE_MODE", "AZURE_DI_ENABLED", "AZURE_DI_ENDPOINT", "AZURE_DI_KEY", "AZURE_DI_MODEL",
    # Google Drive
    "GOOGLE_SERVICE_ACCOUNT_JSON", "GOOGLE_OAUTH_CLIENT_ID",
    "GOOGLE_OAUTH_CLIENT_SECRET", "GOOGLE_OAUTH_REFRESH_TOKEN",
    # OneDrive / Microsoft Graph
    "MS_CLIENT_ID", "MS_TENANT_ID", "MS_CLIENT_SECRET", "MS_DRIVE_USER", "MS_DRIVE_ID",
)


def _load_settings():
    """يطبّق الإعدادات المحفوظة على بيئة العملية عند الإقلاع (قيم الواجهة تغلب)."""
    if not SETTINGS_FILE.exists():
        return
    try:
        saved = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
    except Exception:
        return
    for k, v in saved.items():
        if k in SETTINGS_KEYS and isinstance(v, str) and v:
            os.environ[k] = v


_load_settings()

app = FastAPI(title="خدمة الفحص القانوني الآلي", version="1.0",
              description="معالجة وثائق قانونية عربية (OCR + فهرسة + بطاقات + حزمة) — محلية بالكامل.")

# CORS: يسمح لواجهة العارض (ملف ثابت / GitHub Pages) باستدعاء الخدمة من متصفّح المستخدم.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in os.environ.get("CORS_ORIGINS", "*").split(",") if o.strip()],
    allow_methods=["*"], allow_headers=["*"])

JOBS = {}        # job_id -> {status, created, docs, error}
_LOCK = threading.Lock()


def _auth(key):
    if API_KEY and key != API_KEY:
        raise HTTPException(status_code=401, detail="مفتاح API غير صحيح")


def _process(job_id):
    jd = JOBS_ROOT / job_id
    logs = (jd / "log.txt").open("a", encoding="utf-8")
    def log(m):
        logs.write("%s  %s\n" % (datetime.datetime.now().strftime("%H:%M:%S"), m)); logs.flush()
    try:
        with _LOCK:
            JOBS[job_id]["status"] = "running"
        res = pipeline.run_job(jd, log=log)
        with _LOCK:
            JOBS[job_id].update(status="done", docs=res["docs"])
    except Exception as e:
        log("خطأ: %s" % e)
        with _LOCK:
            JOBS[job_id].update(status="error", error=str(e))
    finally:
        logs.close()


UI_FILE = Path(__file__).resolve().parent / "ui.html"


@app.get("/", include_in_schema=False)
@app.get("/ui", include_in_schema=False)
def ui_page():
    """واجهة الويب: جلب سحابي / رفع ملفات / متابعة المهام / تنزيل النتائج."""
    return HTMLResponse(UI_FILE.read_text(encoding="utf-8"))


@app.get("/health")
def health():
    return {"status": "ok", "time": datetime.datetime.now().isoformat()}


@app.get("/drive/status")
def drive_status(x_api_key: str = ""):
    """أي المزوّدين السحابيين مهيأ (Google / OneDrive) وبأي نمط مصادقة."""
    _auth(x_api_key)
    return cloud_drives.providers_status()


def _azure_status():
    ep = (os.environ.get("AZURE_DI_ENDPOINT")
          or os.environ.get("AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT") or "").strip()
    key = (os.environ.get("AZURE_DI_KEY")
           or os.environ.get("AZURE_DOCUMENT_INTELLIGENCE_KEY") or "").strip()
    on = (os.environ.get("AZURE_DI_ENABLED", "").strip().lower() in ("1", "true", "yes")
          or os.environ.get("ENGINE_MODE", "").strip().lower() == "azure")
    return {"configured": bool(ep and key), "enabled": bool(on and ep and key)}


def _settings_summary():
    return {"keys": {k: bool(os.environ.get(k, "").strip()) for k in SETTINGS_KEYS},
            "drives": cloud_drives.providers_status(), "azure_ocr": _azure_status(),
            "api_key_protected": bool(API_KEY)}


@app.get("/admin/settings")
def get_settings(x_api_key: str = ""):
    """أي المفاتيح مضبوط (دون كشف القيم) + حالة تفعيل OCR السحابي والمزوّدين."""
    _auth(x_api_key)
    return _settings_summary()


class SettingsUpdate(BaseModel):
    """قيم للتحديث: نص فارغ يُتجاهل، وشرطة \"-\" تحذف القيمة المحفوظة."""
    values: dict


@app.post("/admin/settings")
def set_settings(req: SettingsUpdate, x_api_key: str = ""):
    _auth(x_api_key)
    saved = {}
    if SETTINGS_FILE.exists():
        try:
            saved = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
        except Exception:
            saved = {}
    changed = []
    for k, v in (req.values or {}).items():
        if k not in SETTINGS_KEYS or not isinstance(v, str):
            continue
        v = v.strip()
        if not v:
            continue                       # فارغ = لا تغيير (لا يمسح المحفوظ)
        changed.append(k)
        if v == "-":                       # شرطة = حذف صريح
            saved.pop(k, None)
            os.environ.pop(k, None)
        else:
            saved[k] = v
            os.environ[k] = v
    SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
    SETTINGS_FILE.write_text(json.dumps(saved, ensure_ascii=False, indent=1), encoding="utf-8")
    try:
        os.chmod(SETTINGS_FILE, 0o600)
    except Exception:
        pass
    return {"updated": changed, **_settings_summary()}


def _split_list(s: str) -> list:
    return [t.strip() for t in re.split(r"[،,;\n]+", s or "") if t.strip()]


def _write_case_config(job_dir: Path, case_number="", case_title="", parties=None, deed_numbers=None):
    """إعداد قضية مخصّص للمهمّة (اختياري) — يحسّن ربط الأطراف وأرقام الصكوك في التقارير."""
    parties = [p for p in (parties or []) if p and p.strip()]
    deeds = [d for d in (deed_numbers or []) if d and d.strip()]
    if not ((case_number or "").strip() or (case_title or "").strip() or parties or deeds):
        return
    cfg = {"case": {"number": (case_number or "").strip(), "title": (case_title or "").strip()},
           "deed_numbers_known": deeds,
           "parties": {p.strip(): [p.strip()] for p in parties}}
    (job_dir / "case_config.json").write_text(
        json.dumps(cfg, ensure_ascii=False, indent=1), encoding="utf-8")


@app.post("/jobs")
async def create_job(files: list[UploadFile] = File(...), x_api_key: str = "",
                     case_number: str = Form(""), case_title: str = Form(""),
                     parties: str = Form(""), deed_numbers: str = Form("")):
    _auth(x_api_key)
    if not files:
        raise HTTPException(status_code=400, detail="لا ملفات")
    if len(files) > MAX_FILES:
        raise HTTPException(status_code=400, detail="عدد الملفات يتجاوز الحدّ (%d)" % MAX_FILES)
    job_id = uuid.uuid4().hex[:12]
    up = JOBS_ROOT / job_id / "uploads"; up.mkdir(parents=True, exist_ok=True)
    for f in files:
        dest = up / Path(f.filename).name
        with dest.open("wb") as out:
            shutil.copyfileobj(f.file, out)
    _write_case_config(JOBS_ROOT / job_id, case_number, case_title,
                       _split_list(parties), _split_list(deed_numbers))
    with _LOCK:
        JOBS[job_id] = {"status": "queued", "created": datetime.datetime.now().isoformat(),
                        "docs": 0, "error": None}
    threading.Thread(target=_process, args=(job_id,), daemon=True).start()
    return {"job_id": job_id, "status": "queued"}


class DriveRequest(BaseModel):
    """طلب جلب من سحابة: provider = google | onedrive، link = رابط مشاركة أو معرّف مجلد/ملف.
    حقول القضية اختيارية — تحسّن ربط الأطراف والأرقام في التقارير."""
    provider: str
    link: str
    recursive: bool = True
    case_number: str = ""
    case_title: str = ""
    parties: list[str] = []
    deed_numbers: list[str] = []


def _download_then_process(job_id, req: DriveRequest):
    """ينزّل ملفات السحابة إلى uploads ثم يمرّر المهمّة للمعالجة الاعتيادية."""
    jd = JOBS_ROOT / job_id
    up = jd / "uploads"
    logs = (jd / "log.txt").open("a", encoding="utf-8")
    def log(m):
        logs.write("%s  %s\n" % (datetime.datetime.now().strftime("%H:%M:%S"), m)); logs.flush()
    try:
        log("جلب من %s: %s" % (req.provider, req.link))
        paths = cloud_drives.fetch_to_dir(req.provider, req.link, up,
                                          recursive=req.recursive, max_files=MAX_FILES, log=log)
        log("اكتمل التنزيل: %d ملف" % len(paths))
    except Exception as e:
        log("خطأ الجلب السحابي: %s" % e)
        with _LOCK:
            JOBS[job_id].update(status="error", error=str(e))
        logs.close()
        return
    logs.close()
    _process(job_id)


@app.post("/drive/list")
def drive_list(req: DriveRequest, x_api_key: str = ""):
    """معاينة الملفات القابلة للمعالجة تحت الرابط دون تنزيل (للواجهة قبل إنشاء المهمّة)."""
    _auth(x_api_key)
    try:
        items = cloud_drives.list_remote(req.provider, req.link, req.recursive)
    except cloud_drives.DriveError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"count": len(items), "files": items}


@app.post("/jobs/from-drive")
def create_job_from_drive(req: DriveRequest, x_api_key: str = ""):
    """إنشاء مهمّة تُجلب ملفاتها مباشرة من Google Drive أو OneDrive."""
    _auth(x_api_key)
    if req.provider.strip().lower() not in cloud_drives.PROVIDERS:
        raise HTTPException(status_code=400,
                            detail="مزوّد غير مدعوم: %r (المدعوم: google | onedrive)" % req.provider)
    if not req.link.strip():
        raise HTTPException(status_code=400, detail="لا رابط/معرّف")
    job_id = uuid.uuid4().hex[:12]
    (JOBS_ROOT / job_id / "uploads").mkdir(parents=True, exist_ok=True)
    _write_case_config(JOBS_ROOT / job_id, req.case_number, req.case_title,
                       req.parties, req.deed_numbers)
    with _LOCK:
        JOBS[job_id] = {"status": "downloading", "created": datetime.datetime.now().isoformat(),
                        "docs": 0, "error": None, "source": req.provider}
    threading.Thread(target=_download_then_process, args=(job_id, req), daemon=True).start()
    return {"job_id": job_id, "status": "downloading"}


@app.get("/jobs/{job_id}")
def job_status(job_id: str, x_api_key: str = ""):
    _auth(x_api_key)
    if job_id not in JOBS:
        raise HTTPException(status_code=404, detail="مهمّة غير موجودة")
    return JOBS[job_id]


@app.get("/jobs/{job_id}/result")
def job_result(job_id: str, x_api_key: str = ""):
    _auth(x_api_key)
    j = JOBS.get(job_id)
    if not j:
        raise HTTPException(status_code=404, detail="مهمّة غير موجودة")
    if j["status"] != "done":
        return JSONResponse(status_code=409, content={"detail": "غير جاهزة", "status": j["status"]})
    res = JOBS_ROOT / job_id / "result.zip"
    if not res.exists():
        raise HTTPException(status_code=404, detail="لا توجد نتيجة")
    return FileResponse(str(res), media_type="application/zip", filename="legal_package_%s.zip" % job_id)


# خرائط جداول العارض — نفس أسماء ملفات CSV التي ينتجها المحرّك
_VIEWER_TABLES = {"timeline": "08_timeline_gregorian.csv", "deeds": "12_deeds_register.csv",
                  "amounts": "09_central_amounts.csv", "grounds": "10_objection_cassation_grounds.csv",
                  "laws": "11_central_law_references.csv", "milestones": "13_key_milestones.csv"}


@app.get("/jobs/{job_id}/case_data")
def job_case_data(job_id: str, x_api_key: str = ""):
    """نتائج المهمّة بصيغة window.CASE — تستهلكها واجهة تصفّح القضية (زر «☁ سحابة»)."""
    _auth(x_api_key)
    j = JOBS.get(job_id)
    if not j:
        raise HTTPException(status_code=404, detail="مهمّة غير موجودة")
    if j["status"] != "done":
        return JSONResponse(status_code=409, content={"detail": "غير جاهزة", "status": j["status"]})
    src = JOBS_ROOT / job_id / "outputs" / "json" / "full_documents.jsonl"
    if not src.exists():
        raise HTTPException(status_code=404, detail="لا بيانات وثائق لهذه المهمّة")
    try:
        import make_viewer as mv
    except Exception as e:
        raise HTTPException(status_code=500, detail="مولّد العارض غير متاح: %s" % e)
    docs = []
    for line in src.open(encoding="utf-8"):
        line = line.strip()
        if not line:
            continue
        try:
            r = json.loads(line)
        except Exception:
            continue
        title = mv.clean_text(r.get("title", ""))
        ft = mv.fix_reversed_lines(mv.clean_text(r.get("full_text", "") or ""))
        dist = mv._detect_distortion(ft)
        docs.append({"id": r.get("id", ""), "title": title,
                     "doc_type": r.get("doc_type", "غير مصنف"),
                     "parent_path": r.get("parent_path", ""), "viewUrl": r.get("viewUrl", ""),
                     "card": r.get("card", {}) or {}, "entities": r.get("entities", {}) or {},
                     "full_text": ft, "qc": {},
                     "distorted": bool(dist["issues"]), "distReason": "، ".join(dist["issues"]),
                     "hdr": mv.header_footer_lines(ft), "n": len(docs) + 1})
    tables = {}
    csv_dir = JOBS_ROOT / job_id / "outputs" / "csv"
    for key, fname in _VIEWER_TABLES.items():
        p = csv_dir / fname
        if p.exists():
            rows = list(csv.reader(io.StringIO(p.read_text(encoding="utf-8-sig", errors="replace"))))
            if rows:
                tables[key] = {"header": rows[0], "rows": rows[1:]}
    return {"generated": datetime.datetime.now().strftime("%Y-%m-%d %H:%M"),
            "case_number": "", "doc_count": len(docs), "docs": docs,
            "tables": tables, "boiler": mv._boilerplate(docs)}


@app.get("/jobs/{job_id}/log")
def job_log(job_id: str, x_api_key: str = ""):
    _auth(x_api_key)
    p = JOBS_ROOT / job_id / "log.txt"
    return {"log": p.read_text(encoding="utf-8") if p.exists() else ""}
