#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
app.py — خدمة REST API لمحرّك الفحص القانوني (FastAPI).

نمط مهام غير متزامن: ارفع الملفات → احصل على job_id → تابع الحالة → نزّل الحزمة.
كل المعالجة محلية على خادمكم؛ لا تخرج البيانات لأي خدمة خارجية.

التشغيل المحلي:  uvicorn app:app --host 0.0.0.0 --port 8080
التوثيق التفاعلي: GET /docs   (OpenAPI/Swagger يولّده FastAPI تلقائياً)
"""
import os, uuid, shutil, threading, datetime
from pathlib import Path

from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.responses import FileResponse, JSONResponse

import pipeline

JOBS_ROOT = Path(os.environ.get("JOBS_ROOT", "/data/jobs"))
JOBS_ROOT.mkdir(parents=True, exist_ok=True)
API_KEY = os.environ.get("API_KEY", "")          # إن ضُبط، يلزم تمريره بترويسة X-API-Key
MAX_FILES = int(os.environ.get("MAX_FILES", "500"))

app = FastAPI(title="خدمة الفحص القانوني الآلي", version="1.0",
              description="معالجة وثائق قانونية عربية (OCR + فهرسة + بطاقات + حزمة) — محلية بالكامل.")

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


@app.get("/health")
def health():
    return {"status": "ok", "time": datetime.datetime.now().isoformat()}


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


@app.get("/jobs/{job_id}/log")
def job_log(job_id: str, x_api_key: str = ""):
    _auth(x_api_key)
    p = JOBS_ROOT / job_id / "log.txt"
    return {"log": p.read_text(encoding="utf-8") if p.exists() else ""}
