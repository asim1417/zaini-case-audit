#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
azure_engine.py — محرّك OCR سحابي اختياري عبر Azure AI Document Intelligence.

يقرأ PDF/صورة بدقّة عالية (عربي + جداول + تخطيط) ويعيد النص الكامل بترتيب القراءة،
وخياراً جداول الصفحة. يُستخدم لرفع جودة التفريغ فوق سقف Tesseract المحلي.

⚠️ خدمة سحابية: تفعيلها يرسل الوثائق إلى Microsoft Azure (تخرج من البيئة المحلية).
   لا يُفعَّل إلا صراحةً (ENGINE_MODE=azure) ومع ضبط مفتاح/نقطة عبر متغيّرات البيئة.
   لا يُخزَّن أي مفتاح في الكود. تراجع آمن: عند أي تعذّر تُعاد None ويستمر المسار المحلي.

متغيّرات البيئة المطلوبة عند التفعيل:
  ENGINE_MODE=azure
  AZURE_DI_ENDPOINT=https://<اسم-المورد>.cognitiveservices.azure.com/
  AZURE_DI_KEY=<المفتاح>            (الأفضل: استخدام Managed Identity بدل المفتاح في الإنتاج)
  AZURE_DI_MODEL=prebuilt-read       (افتراضي؛ أو prebuilt-layout لاستخراج الجداول)

التثبيت (على الخادم):  pip install azure-ai-documentintelligence
"""
import os
import functools


def available():
    """مفعّل ومتاح؟ (بوابة صريحة + بيانات اعتماد + SDK)."""
    if os.environ.get("ENGINE_MODE", "tesseract").lower() not in ("azure", "azure-di"):
        return False
    if not (os.environ.get("AZURE_DI_ENDPOINT") and os.environ.get("AZURE_DI_KEY")):
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
    return DocumentIntelligenceClient(
        endpoint=os.environ["AZURE_DI_ENDPOINT"].rstrip("/"),
        credential=AzureKeyCredential(os.environ["AZURE_DI_KEY"]),
    )


def ocr_text(file_path):
    """النص الكامل للوثيقة (كل الصفحات) بترتيب القراءة، أو None عند التعذّر."""
    model = os.environ.get("AZURE_DI_MODEL", "prebuilt-read")
    try:
        client = _client()
        with open(file_path, "rb") as fh:
            poller = client.begin_analyze_document(model, body=fh,
                                                   content_type="application/octet-stream")
        result = poller.result()
        # result.content = النص الكامل بترتيب القراءة (يدعم العربية RTL)
        return getattr(result, "content", None) or None
    except Exception:
        return None


def tables(file_path):
    """يعيد جداول الصفحة [(rows مصفوفة خلايا)] عبر prebuilt-layout، أو None."""
    try:
        from azure.ai.documentintelligence import DocumentIntelligenceClient  # noqa
        client = _client()
        with open(file_path, "rb") as fh:
            poller = client.begin_analyze_document("prebuilt-layout", body=fh,
                                                   content_type="application/octet-stream")
        result = poller.result()
        out = []
        for t in (getattr(result, "tables", None) or []):
            grid = [["" for _ in range(t.column_count)] for _ in range(t.row_count)]
            for c in t.cells:
                if c.row_index < t.row_count and c.column_index < t.column_count:
                    grid[c.row_index][c.column_index] = (c.content or "").strip()
            out.append(grid)
        return out or None
    except Exception:
        return None


if __name__ == "__main__":
    print("ENGINE_MODE=azure متاح؟", available())
