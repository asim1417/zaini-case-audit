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

from fastapi import FastAPI, UploadFile, File, HTTPException
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


@app.post("/jobs")
async def create_job(files: list[UploadFile] = File(...), x_api_key: str = ""):
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
    with _LOCK:
        JOBS[job_id] = {"status": "queued", "created": datetime.datetime.now().isoformat(),
                        "docs": 0, "error": None}
    threading.Thread(target=_process, args=(job_id,), daemon=True).start()
    return {"job_id": job_id, "status": "queued"}


class DriveRequest(BaseModel):
    """طلب جلب من سحابة: provider = google | onedrive، link = رابط مشاركة أو معرّف مجلد/ملف."""
    provider: str
    link: str
    recursive: bool = True


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
