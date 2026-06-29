#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
azure_engine.py — محرّك OCR سحابي اختياري عبر Azure AI Document Intelligence.

- يقرأ الإعدادات من البيئة فقط (لا أسرار في الكود).
- يدعم صيغتي المتغيّرات (الأولوية لـ AZURE_DI_*):
    AZURE_DI_ENDPOINT / AZURE_DI_KEY / AZURE_DI_MODEL
    AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT / _KEY / _MODEL
- لا يعمل إلا ببوابة صريحة: ENGINE_MODE=azure أو AZURE_DI_ENABLED=true (المفتاح وحده لا يكفي).
- يدعم prebuilt-read و prebuilt-layout. تراجع آمن: عند أي خطأ يُعاد ناتج فيه error بلا أسرار.
- لا يطبع المفتاح ولا الـendpoint كاملاً.

⚠️ سحابي: التفعيل يرسل الوثيقة إلى Microsoft Azure (تخرج من البيئة المحلية).
"""
import os
import re
import functools
from pathlib import Path


# ---------- تحميل .env تلقائياً (مرة واحدة) من جذر المشروع ----------
def _load_env_once():
    here = Path(__file__).resolve()
    seen = set()
    for base in (here.parent, here.parent.parent, here.parent.parent.parent, Path.cwd()):
        env = base / ".env"
        if env in seen:
            continue
        seen.add(env)
        if env.is_file():
            try:
                from dotenv import load_dotenv
                load_dotenv(env, override=False)
            except Exception:
                for line in env.read_text(encoding="utf-8").splitlines():
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        k, v = line.split("=", 1)
                        os.environ.setdefault(k.strip(), v.strip())
            return  # أوّل .env يُوجَد يكفي


_load_env_once()


# ---------- قراءة الإعداد (الأولوية لـ AZURE_DI_*) ----------
def _endpoint():
    return (os.environ.get("AZURE_DI_ENDPOINT")
            or os.environ.get("AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT") or "").strip().rstrip("/")


def _key():
    return (os.environ.get("AZURE_DI_KEY")
            or os.environ.get("AZURE_DOCUMENT_INTELLIGENCE_KEY") or "").strip()


def _model():
    return (os.environ.get("AZURE_DI_MODEL")
            or os.environ.get("AZURE_DOCUMENT_INTELLIGENCE_MODEL") or "prebuilt-read").strip()


def enabled():
    """بوابة التفعيل الصريحة. وجود المفتاح وحده لا يُفعّل."""
    if os.environ.get("ENGINE_MODE", "tesseract").lower() in ("azure", "azure-di"):
        return True
    return os.environ.get("AZURE_DI_ENABLED", "").strip().lower() in ("1", "true", "yes")


def configured():
    """نقطة + مفتاح مضبوطان (بأي من الصيغتين)؟"""
    return bool(_endpoint() and _key())


def available():
    """مفعّل + مُهيّأ + SDK متاح."""
    if not (enabled() and configured()):
        return False
    try:
        _client()
        return True
    except Exception:
        return False


@functools.lru_cache(maxsize=1)
def _client():
    from azure.ai.documentintelligence import DocumentIntelligenceClient
    from azure.core.credentials import AzureKeyCredential
    return DocumentIntelligenceClient(endpoint=_endpoint(), credential=AzureKeyCredential(_key()))


def _redact(msg):
    """يخفي المفتاح والـendpoint من أي رسالة خطأ."""
    s = str(msg)
    k = _key()
    if k:
        s = s.replace(k, "***KEY***")
    ep = _endpoint()
    if ep:
        s = s.replace(ep, "***ENDPOINT***")
    # احذف أي توقيعات/مفاتيح اشتراك محتملة
    s = re.sub(r"(Ocp-Apim-Subscription-Key|key|sig|signature)\s*[:=]\s*\S+", r"\1=***", s, flags=re.I)
    return s[:300]


def analyze(path):
    """يحلّل وثيقة عبر Azure ويعيد ناتجاً موحّداً (بلا أسرار):
       {engine, model, text, pages, page_count, tables, confidence, error}"""
    model = _model()
    out = {"engine": "azure-document-intelligence", "model": model, "text": "",
           "pages": [], "page_count": 0, "tables": [], "confidence": None, "error": None}
    try:
        client = _client()
        with open(path, "rb") as fh:
            poller = client.begin_analyze_document(model, body=fh,
                                                   content_type="application/octet-stream")
        result = poller.result()
        out["text"] = getattr(result, "content", "") or ""
        pgs = getattr(result, "pages", None) or []
        out["page_count"] = len(pgs)
        for p in pgs:
            lines = getattr(p, "lines", None) or []
            out["pages"].append("\n".join(getattr(l, "content", "") or "" for l in lines))
        # الجداول (تظهر مع prebuilt-layout)
        for t in (getattr(result, "tables", None) or []):
            rc, cc = getattr(t, "row_count", 0), getattr(t, "column_count", 0)
            grid = [["" for _ in range(cc)] for _ in range(rc)]
            for cell in getattr(t, "cells", None) or []:
                ri, ci = getattr(cell, "row_index", 0), getattr(cell, "column_index", 0)
                if ri < rc and ci < cc:
                    grid[ri][ci] = (getattr(cell, "content", "") or "").strip()
            out["tables"].append(grid)
        # متوسط الثقة (إن توفّر على مستوى الكلمات)
        confs = [getattr(w, "confidence", None) for p in pgs for w in (getattr(p, "words", None) or [])
                 if getattr(w, "confidence", None) is not None]
        out["confidence"] = round(sum(confs) / len(confs), 3) if confs else None
        return out
    except Exception as e:
        out["error"] = "%s: %s" % (type(e).__name__, _redact(e))
        return out


def ocr_text(path):
    """النص الكامل عبر Azure، أو None عند التعذّر (للاستخدام في pipeline)."""
    r = analyze(path)
    if r.get("error") or not (r.get("text") or "").strip():
        return None
    return r["text"]


if __name__ == "__main__":
    print("enabled:", enabled(), "| configured:", configured(), "| model:", _model(),
          "| endpoint set:", bool(_endpoint()))
