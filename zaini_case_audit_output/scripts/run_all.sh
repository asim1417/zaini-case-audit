#!/usr/bin/env bash
# =====================================================================
# run_all.sh — أمر واحد يشغّل فحص كل مستندات قضية زيني 42824717 من البداية للنهاية
# الاستخدام:
#   bash scripts/run_all.sh
# (يفترض أن مجلد staging موجود بداخله text/ و parts/ و study/source_study.docx)
# =====================================================================
set -euo pipefail

# اذهب إلى جذر المخرجات (المجلد الأب لـ scripts)
cd "$(dirname "$0")/.."
ROOT="$(pwd)"
STAGING="$ROOT/staging"
STUDY="$STAGING/study/source_study.docx"
SC="$ROOT/scripts"

echo "=========================================================="
echo " فحص شامل لكل مستندات قضية زيني 42824717 — أمر واحد"
echo " المجلد: $ROOT"
echo "=========================================================="

if [ ! -d "$STAGING/text" ]; then
  echo "خطأ: لا يوجد staging/text. يلزم تجهيز النصوص أولاً." >&2; exit 1
fi

# 0) معالجة الملفات الثنائية (فكّ ضغط + OCR) — تُشغَّل فقط عند تمرير --with-binaries
#    (مكلفة زمنياً؛ تلزم مرة واحدة عند إضافة أرشيفات/صور جديدة إلى staging/raw)
if [ "${1:-}" = "--with-binaries" ] && [ -d "$STAGING/raw" ] && \
   [ -n "$(ls -A "$STAGING/raw" 2>/dev/null || true)" ]; then
  echo; echo ">> [0/8] معالجة الملفات الثنائية (فكّ ضغط + OCR)..."
  python3 "$SC/process_binaries.py" "$STAGING" || echo "  (تخطّي: لا ملفات ثنائية صالحة)"
else
  echo; echo ">> [0/8] تخطّي معالجة الملفات الثنائية (مرّر --with-binaries لتفعيلها)"
fi

echo; echo ">> [0-أ] فهرسة تلقائية عند الحاجة..."
python3 "$SC/auto_index.py" "$STAGING" || true

echo; echo ">> [1/8] تحسين قراءة النصوص (تمريرة 1 + اكتشاف أسماء الأطراف + تمريرة 2)..."
python3 "$SC/improve_readability.py" "$STAGING"
python3 "$SC/detect_parties.py" "$STAGING" || true
python3 "$SC/improve_readability.py" "$STAGING"

echo; echo ">> [2/8] بناء فهرس المستندات الـ192 من الدراسة..."
if [ -f "$STUDY" ]; then
  python3 "$SC/build_study_index.py" "$STUDY" "$STAGING" | tail -1
else
  echo "  تحذير: ملف الدراسة غير موجود ($STUDY) — تخطّي إعادة بناء الفهرس."
fi

echo; echo ">> [3/8] الفحص الآلي (استخراج وتصنيف الكيانات)..."
python3 "$SC/audit_zaini_case.py" --staging "$STAGING" 2>/dev/null | grep -E "اكتمل" || true

echo; echo ">> [4/8] التحليل (خط زمني + أسباب نقض + مبالغ + إحالات)..."
python3 "$SC/analyze_case.py" --staging "$STAGING" 2>/dev/null | tail -1

echo; echo ">> [5/8] الموجز الموحّد + سجل الصكوك + المحطات..."
python3 "$SC/case_brief.py" --staging "$STAGING" 2>/dev/null | tail -1

echo; echo ">> [6/8] توليد ملفات Word (تقارير + مستند لكل وثيقة)..."
python3 "$SC/make_word.py" --staging "$STAGING" 2>/dev/null | tail -1

echo; echo ">> [7/8] توليد الفهرس الرئيسي Excel (00_master_documents)..."
python3 "$SC/make_master_excel.py" --staging "$STAGING" 2>/dev/null | grep "أُنشئ"

echo; echo ">> [8/8] فحص الجودة الآلي لكل ملف..."
python3 "$SC/qc_readability.py" "$STAGING" 2>/dev/null | grep -E "فُحص|سليم|معكوسة|تشويش|التقرير"

echo
echo "=========================================================="
echo " اكتمل الفحص الشامل. أهم المخرجات:"
echo "  - الفهرس:   outputs/excel/00_master_documents.xlsx"
echo "  - الموجز:   outputs/word/00_ملخص_القضية.docx"
echo "  - الوثائق:  outputs/word/documents/  (ملف لكل مستند)"
echo "  - الجودة:   outputs/csv/14_readability_qc.csv"
echo "  - JSON:     outputs/json/full_audit_data.json"
echo "=========================================================="
