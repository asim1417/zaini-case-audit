#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
lift_engine.py — محرّك استخراج مهيكل اختياري عبر نموذج Datalab «lift» (رؤية، 9B).

يستخدم schema-constrained decoding + الامتناع المدرّب (يعيد null عند غياب الحقل
بدل الاختلاق) — متوافق مع مبدأ المنظومة «لا تختلق نصاً».

اختياري وخلف بوابة: لا يعمل إلا إذا ENGINE_MODE=lift وكان النموذج مثبّتاً (يتطلّب GPU).
الافتراضي يبقى Tesseract المحلي (CPU). إن تعذّر تحميل lift، تُعاد None ويستمر المسار الحالي.

الترخيص: نسخة OpenRAIL-M المعدّلة (مجاني للبحث/الشخصي/الشركات < 5M$ إيراد) — تحقّق قبل الاستخدام التجاري.
التثبيت (على خادم GPU):  pip install lift-extract   (أو من github.com/datalab-to/lift)
"""
import os, json, functools

# ---- قوالب JSON Schema (تُمرَّر للنموذج فيلتزم بها حرفياً) ----
CARD_SCHEMA = {
    "type": "object",
    "properties": {
        "نوع_المستند": {"type": ["string", "null"]},
        "الجهة_المصدرة": {"type": ["string", "null"]},
        "الدائرة": {"type": ["string", "null"]},
        "رقم_القضية": {"type": ["string", "null"]},
        "رقم_الصك_أو_الحكم": {"type": ["string", "null"]},
        "التاريخ_الهجري": {"type": ["string", "null"]},
        "التاريخ_الميلادي": {"type": ["string", "null"]},
        "الأطراف": {"type": "array", "items": {"type": "string"}},
        "يوجد_ختم_أو_توقيع": {"type": ["boolean", "null"]},
    },
    "required": ["نوع_المستند", "رقم_القضية", "التاريخ_الهجري", "الأطراف"],
}

FINANCIAL_SCHEMA = {
    "type": "object",
    "properties": {
        "العملة": {"type": ["string", "null"]},
        "المبالغ": {
            "type": "array",
            "items": {"type": "object", "properties": {
                "الوصف": {"type": ["string", "null"]},
                "القيمة": {"type": ["number", "null"]},
                "السنة": {"type": ["string", "null"]},
            }, "required": ["القيمة"]},
        },
        "الإجمالي": {"type": ["number", "null"]},
    },
    "required": ["المبالغ"],
}


def available():
    """هل المحرّك مفعّل ومتاح؟ (بوابة صريحة + استيراد ناجح)."""
    if os.environ.get("ENGINE_MODE", "tesseract").lower() != "lift":
        return False
    try:
        _load()
        return True
    except Exception:
        return False


@functools.lru_cache(maxsize=1)
def _load():
    """تحميل النموذج مرّة واحدة (يتطلّب GPU + الحزمة مثبّتة)."""
    from lift import Lift  # type: ignore  (حزمة datalab-to/lift)
    model_id = os.environ.get("LIFT_MODEL", "datalab-to/lift")
    return Lift(model_id)


def extract(pdf_or_image_path, schema):
    """يعيد dict مطابقاً للـschema (مع null للحقول الغائبة)، أو None عند التعذّر.
    schema: dict (JSON Schema). لا اختلاق — الامتناع المدرّب يعيد null."""
    try:
        model = _load()
        return model.extract(schema=schema, file=str(pdf_or_image_path))
    except Exception:
        return None


def card_from_lift(pdf_or_image_path):
    """بطاقة تعريف عبر lift → بصيغة مفاتيح المنظومة العربية. None عند التعذّر."""
    r = extract(pdf_or_image_path, CARD_SCHEMA)
    if not r:
        return None
    greg = r.get("التاريخ_الميلادي"); hij = r.get("التاريخ_الهجري")
    card = {}
    m = {"نوع_المستند": "نوع المستند", "الجهة_المصدرة": "الجهة المصدِرة",
         "الدائرة": "الدائرة", "رقم_القضية": "رقم القضية",
         "رقم_الصك_أو_الحكم": "رقم الصك/الحكم"}
    for k, label in m.items():
        if r.get(k):
            card[label] = r[k]
    if hij or greg:
        card["التاريخ"] = hij or greg
    if r.get("الأطراف"):
        card["الأطراف"] = "، ".join(r["الأطراف"])
    return card


def figures_from_lift(pdf_or_image_path):
    """مبالغ مالية عبر lift → قائمة (الوصف، القيمة). None عند التعذّر."""
    r = extract(pdf_or_image_path, FINANCIAL_SCHEMA)
    if not r:
        return None
    cur = r.get("العملة") or ""
    out = []
    for it in (r.get("المبالغ") or []):
        v = it.get("القيمة")
        if v is None:
            continue
        ctx = it.get("الوصف") or "—"
        val = ("{:,}".format(v) if isinstance(v, (int, float)) else str(v)) + ((" " + cur) if cur else "")
        out.append((ctx, val))
    return out


if __name__ == "__main__":
    import sys
    print("ENGINE_MODE=lift متاح؟", available())
    print(json.dumps(CARD_SCHEMA, ensure_ascii=False, indent=1))
