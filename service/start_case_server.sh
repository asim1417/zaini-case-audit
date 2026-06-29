#!/usr/bin/env bash
# start_case_server.sh — يبني قاعدة البيانات إن لزم ثم يشغّل خادم القضية.
# متغيّرات: CASE_JSONL (مصدر الوثائق) · CASE_DB (مسار القاعدة) · APP_PASSWORD (إلزامي) · PORT
set -e
cd "$(dirname "$0")"
: "${CASE_DB:=case.db}"
: "${CASE_JSONL:=full_documents.jsonl}"
: "${PORT:=8080}"

if [ -z "$APP_PASSWORD" ]; then
  echo "✗ اضبط APP_PASSWORD (كلمة مرور الدخول) في إعدادات الاستضافة."; exit 1
fi
if [ ! -f "$CASE_DB" ]; then
  if [ -f "$CASE_JSONL" ]; then
    echo "بناء قاعدة البيانات من $CASE_JSONL ..."
    python build_case_db.py "$CASE_JSONL" "$CASE_DB"
  else
    echo "✗ لا توجد $CASE_DB ولا $CASE_JSONL — ارفع full_documents.jsonl أو القاعدة."; exit 1
  fi
fi
exec python -m uvicorn case_server:app --host 0.0.0.0 --port "$PORT"
