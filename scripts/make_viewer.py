#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
make_viewer.py — توليد واجهة تصفّح أمامية (HTML) لمخرجات الفحص.

ينتج viewer/index.html + viewer/case_data.js. يعمل محلياً وعلى GitHub Pages.
ميزات: بحث عربي مُطبَّع/منطقي، تنقّل بين المطابقات، ترقيم أسطر، مقتطفات وملاحظات
وأعلام مراجعة (محفوظة محلياً) وتصديرها، مؤشّر جودة القراءة، تحويل تاريخ هجري/ميلادي،
فرز وتجميع، وضع قراءة واختصارات، جسر «جهّز سؤالاً لكلود»، قفل بكلمة مرور (تشفير محلي)،
تعدّد القضايا، رسوم بصرية، وتصدير Word/PDF/HTML/CSV.

كل المخرجات «مساعدة آلية تحتاج مراجعة بشرية».
"""
import os, re, json, csv, io, datetime
from pathlib import Path

# تنظيف النص: إزالة علامات الاتجاه الخفية + توحيد الحروف/الأرقام الفارسية إلى العربية (بلا حذف محتوى).
_STRIP = dict.fromkeys([0x200b, 0x200c, 0x200d, 0x200e, 0x200f, 0x202a, 0x202b,
                        0x202c, 0x202d, 0x202e, 0x2066, 0x2067, 0x2068, 0x2069, 0xfeff], None)
_LOOK = {"ھ": "ه", "ہ": "ه", "ۀ": "ه", "ۃ": "ة", "ی": "ي", "ۍ": "ي", "ک": "ك"}
_PDIG = {0x06F0 + i: chr(0x0660 + i) for i in range(10)}


def clean_text(t):
    if not t:
        return t
    t = t.translate(_STRIP)
    for a, b in _LOOK.items():
        t = t.replace(a, b)
    return t.translate(_PDIG)


def _cnorm(s):
    o = []
    for c in s:
        k = ord(c)
        if 0x064B <= k <= 0x0652 or k in (0x0640, 0x0670):
            continue
        o.append({"أ": "ا", "إ": "ا", "آ": "ا", "ة": "ه", "ى": "ي", "ؤ": "و", "ئ": "ي"}.get(c, c))
    return "".join(o)


# كلمات عربية شائعة: تظهر في النص الصحيح لا المعكوس — للكشف عن الأسطر المقلوبة اتجاهياً (OCR).
_COMMON = set(_cnorm(w) for w in (
    "من في على الى عن ان انه اذا الذي التي هذا هذه ذلك ولا وقد قد كان بعد قبل حيث لدى "
    "الله المدعي المدعى المحكمة الدعوى الحكم بيع حصص ريال العقد التاريخ رقم صك وزارة "
    "العدل المملكة العربية السعودية الطرف الوكالة النظام المادة بموجب بتاريخ الموافق "
    "هو هي نحن انا وعلى وفي كما ثم او اي بن بنت الشيخ عن نفسه اصالة").split())


def fix_reversed_lines(text):
    """يعيد الأسطر المقلوبة اتجاهياً (فارطلأا → الأطراف) إلى وضعها الصحيح، بلا حذف.
       يقلب السطر فقط إذا احتوى معكوسه كلمات شائعة أكثر بوضوح (كشف نسبي محافظ)."""
    out = []
    for l in text.split("\n"):
        toks = re.findall(r'[ء-ي]{2,}', l)
        if len(toks) >= 5 and " " in l.strip():
            oh = sum(1 for w in toks if _cnorm(w) in _COMMON)
            rt = re.findall(r'[ء-ي]{2,}', l[::-1])
            rh = sum(1 for w in rt if _cnorm(w) in _COMMON)
            if rh >= 3 and rh >= oh + 3:
                out.append(l[::-1]); continue
        out.append(l)
    return "\n".join(out)


# كشف الترويسات/التذييلات بحسب حدود الصفحات (علامات [صفحة N]) — أدقّ من التكرار الحرفي.
_PM = re.compile(r'^\s*\[\s*صفح[ةه]\s*\d+\s*\]')
# كلمات بنية الترويسة الرسمية (تُخفّت حتى لو كانت كلمات صحيحة: أسماء محاكم/دوائر/أرقام)
_HDR_KW = re.compile(r'المملك|العربي[ةه]\s*السعودي|وزار[ةه]\s*العدل|ديوان\s*المظالم|المحكم|الدائر[ةه]|'
                     r'كتاب[ةه]\s*العدل|النياب[ةه]\s*العام|مجلس\s*القضاء|صك\s*رقم|رقم\s*الصك|'
                     r'رقم\s*القضي|رقم\s*المعامل|رقم\s*الصفح|صفح[ةه]\s*\d|هيئ[ةه]\s*النظر|'
                     r'بريد\s*ال[كإ]لكترون|هاتف|فاكس|ص\.?\s*ب\b|www\.|https?:|المركز\s*الوطني')
# بدايات المتن — نتوقّف عن اعتبار السطر ترويسة عندها (لكل عائلة)
_BODY_START = re.compile(r'بسم\s*الله|الحمد\s*لل[ةه]|ان[ةه]\s*في\s*يوم|لد[يى]\s*ان[اى]|بناء\s*عل[يى]|'
                         r'وبعد|الوقائع|اسباب\s*الحكم|منطوق|حيث\s*ان|نظرن?ا|القرار|تتلخص|'
                         r'المدع[يى]|الطلب|قررت\s*المحكم|السلام\s*عليكم|صاحب\s*السمو|سعادة')


def _garbled(s):
    """سطر مشوّه/غير نصّي: أغلب رموزه قصيرة أو قليلة الحروف (فُتات OCR)."""
    toks = re.findall(r'[ء-ي]+', s)
    letters = len(re.sub(r'[^ء-ي]', '', s))
    if not toks:
        return True
    short = sum(1 for w in toks if len(w) <= 2)
    return letters <= 4 or short / len(toks) >= 0.6


def header_footer_lines(text):
    """كشف موحّد البنية: يخفّت صدر كل صفحة (ترويسة العائلة الرسمية) حتى بداية المتن،
       ويخفّت التذييلات حول علامات الصفحات، ويلتقط سطور الترويسة القوية أينما وردت."""
    lines = text.split("\n"); n = len(lines); hf = set()
    starts = [0] + [i + 1 for i, l in enumerate(lines) if _PM.match(l)]
    for st in starts:
        j, k = st, 0
        while j < n and k < 12 and not _PM.match(lines[j]):
            s = lines[j].strip()
            if not s:
                j += 1; continue
            if _BODY_START.search(s):
                break  # بدأ المتن — لا تخفّت بعده
            letters = len(re.sub(r'[^ء-ي]', '', s))
            is_hdr = bool(_HDR_KW.search(s)) or _garbled(s) or bool(re.match(r'^[\d\s٠-٩.,\-/:]+$', s))
            if is_hdr:
                hf.add(j); k += 1; j += 1
            elif letters >= 20:
                break  # سطر محتوى حقيقي طويل
            else:
                hf.add(j); k += 1; j += 1  # سطر قصير غامض بين ترويسات
    # تذييلات: أسطر قبل علامات الصفحات (أرقام/فُتات/كلمات ترويسة)
    for i, l in enumerate(lines):
        if not _PM.match(l):
            continue
        j, k = i - 1, 0
        while j >= 0 and k < 3:
            s = lines[j].strip()
            if not s:
                j -= 1; continue
            if _garbled(s) or re.match(r'^[\d\s٠-٩.,\-/]+$', s) or _HDR_KW.search(s):
                hf.add(j); k += 1; j -= 1
            else:
                break
    # سطور ترويسة قوية قصيرة أينما وردت (تذييلات وسط المستند)
    for j, l in enumerate(lines):
        s = l.strip()
        if s and len(s) <= 34 and _HDR_KW.search(s):
            hf.add(j)
    return sorted(hf)

SCRIPT_DIR = Path(__file__).resolve().parent
OUTPUT_ROOT = Path(os.environ.get("CASE_ROOT") or SCRIPT_DIR.parent)
OUT = OUTPUT_ROOT / "outputs"
VIEWER = OUTPUT_ROOT / "viewer"
DOCS_JSONL = OUT / "json" / "full_documents.jsonl"
CSV_DIR = OUT / "csv"


def load_qc():
    p = CSV_DIR / "14_readability_qc.csv"
    qc = {}
    if not p.exists():
        return qc
    rows = list(csv.reader(io.StringIO(p.read_text(encoding="utf-8-sig", errors="replace"))))
    if not rows:
        return qc
    h = rows[0]
    def idx(name):
        for i, c in enumerate(h):
            if name in c:
                return i
        return -1
    iT, iS, iR, iA, iW = idx("الملف"), idx("الحالة"), idx("معكوسة"), idx("نسبة"), idx("كلمات")
    for r in rows[1:]:
        if iT < 0 or iT >= len(r):
            continue
        qc[r[iT].strip()] = {
            "status": r[iS] if 0 <= iS < len(r) else "",
            "rev": r[iR] if 0 <= iR < len(r) else "",
            "ratio": r[iA] if 0 <= iA < len(r) else "",
            "words": r[iW] if 0 <= iW < len(r) else "",
        }
    return qc


def load_docs(qc):
    docs = []
    if not DOCS_JSONL.exists():
        return docs
    for line in DOCS_JSONL.open(encoding="utf-8"):
        line = line.strip()
        if not line:
            continue
        try:
            r = json.loads(line)
        except Exception:
            continue
        title = clean_text(r.get("title", ""))
        ft = fix_reversed_lines(clean_text(r.get("full_text", "") or ""))
        dist = _detect_distortion(ft)
        docs.append({
            "id": r.get("id", ""), "title": title,
            "doc_type": r.get("doc_type", "غير مصنف"),
            "parent_path": r.get("parent_path", ""), "viewUrl": r.get("viewUrl", ""),
            "card": r.get("card", {}) or {}, "entities": r.get("entities", {}) or {},
            "full_text": ft,
            "qc": qc.get(title) or qc.get(title.rsplit(".", 1)[0]) or {},
            "distorted": bool(dist["issues"]), "distReason": "، ".join(dist["issues"]),
            "hdr": header_footer_lines(ft),
            "n": len(docs) + 1,
        })
    return docs


# كشف التشوّه — نفس منطق حزمة الوثائق (رموز غريبة + تكرار حروف + فُتات أسطر).
_BAD_SYMS = re.compile(r"[�□￯]")


def _detect_distortion(text):
    syms = len(_BAD_SYMS.findall(text))
    reps = len(re.findall(r"(\S)\1{3,}", text))
    frags = sum(1 for l in text.split("\n") if 0 < len(l.strip()) <= 2)
    issues = []
    if syms:
        issues.append("رموز غريبة: %d" % syms)
    if reps:
        issues.append("تكرار حروف: %d" % reps)
    if frags > 5:
        issues.append("فُتات أسطر: %d" % frags)
    return {"issues": issues}


def load_csv(name):
    p = CSV_DIR / name
    if not p.exists():
        return None
    rows = list(csv.reader(io.StringIO(p.read_text(encoding="utf-8-sig", errors="replace"))))
    if not rows:
        return None
    return {"header": rows[0], "rows": rows[1:]}


def _pynorm(s):
    out = []
    for ch in s:
        c = ord(ch)
        if 0x064B <= c <= 0x0652 or c in (0x0640, 0x0670):
            continue
        if ch in "أإآٱ":
            out.append("ا")
        elif ch == "ة":
            out.append("ه")
        elif ch == "ى":
            out.append("ي")
        elif ch == "ؤ":
            out.append("و")
        elif ch == "ئ":
            out.append("ي")
        else:
            out.append(ch.lower())
    return "".join(out)


_AR = re.compile(r"[؀-ۿ]")


def _is_phrase(t):
    """عبارة عربية حقيقية (ترويسة محتملة) لا فُتات أرقام/رموز."""
    words = [w for w in t.split() if len(_AR.findall(w)) >= 2]
    body = t.replace(" ", "")
    return len(words) >= 2 and body and (len(_AR.findall(t)) / len(body)) >= 0.55


def _boilerplate(docs):
    """أسطر الترويسة/التذييل المتكرّرة عبر كثير من الوثائق (boilerplate) — للتخفيت في العرض، بلا حذف.
       نحصرها في العبارات العربية الحقيقية المتكرّرة، لا فُتات OCR الرقمية."""
    from collections import Counter
    cnt = Counter()
    for d in docs:
        seen = set()
        for raw in (d.get("full_text", "") or "").split("\n"):
            t = _pynorm(raw.strip())
            if 6 <= len(t) <= 80 and t not in seen and _is_phrase(t):
                seen.add(t)
                cnt[t] += 1
    thr = max(10, int(len(docs) * 0.06))
    return sorted([t for t, c in cnt.items() if c >= thr])


def main():
    qc = load_qc()
    docs = load_docs(qc)
    tables = {}
    for key, fname in {
        "timeline": "08_timeline_gregorian.csv", "deeds": "12_deeds_register.csv",
        "amounts": "09_central_amounts.csv", "grounds": "10_objection_cassation_grounds.csv",
        "laws": "11_central_law_references.csv", "milestones": "13_key_milestones.csv",
    }.items():
        t = load_csv(fname)
        if t:
            tables[key] = t
    case_no = ""
    cfg = OUTPUT_ROOT / "case_config.json"
    if cfg.exists():
        try:
            case_no = json.loads(cfg.read_text(encoding="utf-8")).get("case", {}).get("number", "")
        except Exception:
            pass
    data = {"generated": datetime.datetime.now().strftime("%Y-%m-%d %H:%M"),
            "case_number": case_no, "doc_count": len(docs), "docs": docs, "tables": tables,
            "boiler": _boilerplate(docs)}

    VIEWER.mkdir(parents=True, exist_ok=True)
    (VIEWER / "case_data.js").write_text("window.CASE = " + json.dumps(data, ensure_ascii=False) + ";\n", encoding="utf-8")

    shell_js = json.dumps(APP_SHELL).replace("</", "<\\/")
    # لا نستدعي startApp هنا (قد يسبق تعريفه)؛ الاستدعاء في نهاية سكربت التطبيق
    boot = ('<script>window.APP_SHELL=' + shell_js + ';</script>\n<script src="case_data.js"></script>\n<script src="case_morph.js"></script>\n<script src="case_suspects.js"></script>')
    # نستبدل أول وسم فقط؛ الوسم الثاني داخل دالة القفل يبقى نصاً ليعمل وقت التشغيل
    index_html = APP_SHELL.replace("__BOOTSTRAP__", boot, 1)
    (VIEWER / "index.html").write_text(index_html, encoding="utf-8")
    print("viewer ready:", VIEWER, "| docs:", len(docs), "| tables:", list(tables.keys()))


# ملاحظة: __BOOTSTRAP__ يُستبدل عند التوليد بمحمّل البيانات + APP_SHELL مضمّناً
# (لإتاحة بناء نسخة مقفلة بكلمة مرور من داخل الصفحة).
APP_SHELL = r"""<!DOCTYPE html>
<html lang="ar" dir="rtl">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>واجهة تصفّح القضية — مخرج آلي يحتاج مراجعة بشرية</title>
<style>
  :root{--bg:#f6f7f9;--pane:#fff;--ink:#1f2937;--mut:#6b7280;--line:#e5e7eb;
        --accent:#2563eb;--accent2:#eff6ff;--warn:#fde68a;--chip:#f1f5f9;
        --tsize:18px;--tlh:1.9;--tfam:"Traditional Arabic","Simplified Arabic","Arabic Typesetting","Amiri",Tahoma,serif;--talign:justify;}
  body.dark{--bg:#0f172a;--pane:#1e293b;--ink:#e5e7eb;--mut:#94a3b8;--line:#334155;--accent:#3b82f6;--accent2:#1e3a5f;--chip:#243449}
  body.dark mark{background:#854d0e;color:#fff}
  body.paper{--bg:#efe6d2;--pane:#fbf5e6;--ink:#3a2f1d;--mut:#8a7a5c;--line:#e0d4ba;--accent2:#f3ead2}
  /* تلوين ذكي للنص */
  .e-amt{color:#15803d;font-weight:600}
  .e-date{color:#1d4ed8}
  .e-num{color:#7c3aed}
  .e-party{color:#c2410c;font-weight:600}
  u.susp{text-decoration:underline wavy #dc2626;text-decoration-skip-ink:none;cursor:help}
  body.dark .e-amt{color:#4ade80}body.dark .e-date{color:#93c5fd}body.dark .e-num{color:#c4b5fd}body.dark .e-party{color:#fdba74}
  .statwrap{padding:6px 16px 30px}.statwrap h3{margin:14px 0 6px}
  .sbar{display:flex;align-items:center;gap:8px;margin:3px 0;font-size:13.5px}
  .sbar .lbl{width:170px;flex:none;cursor:pointer}.sbar .lbl:hover{color:var(--accent)}
  .sbar .bb{height:16px;background:var(--accent);border-radius:4px;min-width:3px}
  .sbar .cnt{color:var(--mut);font-size:12px}
  *{box-sizing:border-box}
  body{margin:0;font-family:"Segoe UI",Tahoma,Arial,sans-serif;background:var(--bg);color:var(--ink);font-size:15px;line-height:1.7}
  body.reading .side{display:none}
  header{background:var(--pane);border-bottom:1px solid var(--line);padding:8px 14px;display:flex;gap:10px;align-items:center;flex-wrap:wrap;position:sticky;top:0;z-index:6}
  header h1{font-size:16px;margin:0}
  .banner{background:var(--warn);color:#7c2d12;font-size:12px;padding:3px 9px;border-radius:6px}
  .meta{color:var(--mut);font-size:12px;margin-inline-start:auto}
  .bar{display:flex;gap:6px;align-items:center;flex-wrap:wrap;font-size:12.5px;color:var(--mut)}
  .grp{display:flex;gap:2px;align-items:center;background:var(--bg);border:1px solid var(--line);border-radius:8px;padding:2px 6px}
  .grp button{border:none;background:transparent;cursor:pointer;font-size:13px;padding:1px 6px;border-radius:6px}
  .grp button:hover{background:var(--accent2)}
  .grp select,.grp input{border:none;background:transparent;font-family:inherit;font-size:12.5px;cursor:pointer}
  .tabs{display:flex;gap:6px;flex-wrap:wrap;padding:8px 14px 0}
  .tab{padding:6px 13px;border:1px solid var(--line);background:var(--pane);border-radius:20px;cursor:pointer;font-size:13px}
  .tab.active{background:var(--accent);color:#fff;border-color:var(--accent)}
  .wrap{display:flex;height:calc(100vh - 96px)}
  .side{width:380px;min-width:280px;background:var(--pane);border-inline-start:1px solid var(--line);display:flex;flex-direction:column}
  .controls{padding:9px;border-bottom:1px solid var(--line)}
  .srchopts{display:flex;flex-wrap:wrap;gap:4px 12px;font-size:12.5px;margin-bottom:5px}
  .srchopts label{white-space:nowrap;display:flex;align-items:center;gap:3px;cursor:pointer}
  /* الوصولية (WCAG) */
  .sr-only{position:absolute;width:1px;height:1px;padding:0;margin:-1px;overflow:hidden;clip:rect(0,0,0,0);white-space:nowrap;border:0}
  .skip{position:absolute;right:10px;top:-48px;background:var(--accent);color:#fff;padding:9px 14px;border-radius:8px;z-index:30;transition:top .15s}
  .skip:focus{top:10px}
  :focus-visible{outline:3px solid #2563eb;outline-offset:2px}
  .item:focus-visible,.tab:focus-visible{outline:3px solid #2563eb;outline-offset:-2px}
  @media (prefers-reduced-motion:reduce){*{transition:none!important}}
  .controls input[type=text],.controls select{width:100%;padding:7px 9px;border:1px solid var(--line);border-radius:8px;font-size:14px;margin-bottom:5px;font-family:inherit}
  .row{display:flex;gap:5px;align-items:center;flex-wrap:wrap;font-size:12.5px;margin-bottom:4px}
  .row button{padding:4px 8px;border:1px solid var(--line);background:var(--pane);border-radius:7px;cursor:pointer;font-size:12.5px}
  .row button:hover{background:var(--accent2)}
  .btn-export{background:var(--accent)!important;color:#fff;border-color:var(--accent)!important;font-weight:600}
  .selcount{color:var(--accent);font-weight:600}
  .hint{font-size:11px;color:var(--mut)}
  .count{font-size:12px;color:var(--mut);padding:2px 4px}
  .list{overflow:auto;flex:1}
  .grphead{padding:5px 10px;background:var(--accent2);font-size:12px;font-weight:700;cursor:pointer;position:sticky;top:0}
  .item{padding:8px 10px;border-bottom:1px solid var(--line);cursor:pointer;display:flex;gap:7px;align-items:flex-start}
  .item:hover{background:var(--accent2)}
  .item.active{background:var(--accent2);border-inline-start:3px solid var(--accent)}
  .item input{margin-top:3px;flex:none;width:15px;height:15px;cursor:pointer}
  .item .t{font-size:13px;font-weight:600;word-break:break-word}
  .item .s{font-size:11px;color:var(--mut);margin-top:2px}
  .dot{display:inline-block;width:8px;height:8px;border-radius:50%;margin-inline-start:4px}
  .dot.ok{background:#16a34a}.dot.warn{background:#f59e0b}.dot.bad{background:#dc2626}
  .flag{font-size:11px}
  main{flex:1;overflow:auto;padding:16px 20px}
  .card{background:var(--pane);border:1px solid var(--line);border-radius:12px;padding:13px 15px;margin-bottom:12px}
  .card h2{margin:0 0 8px;font-size:16px}
  .kv{display:grid;grid-template-columns:140px 1fr;gap:4px 12px;font-size:13.5px}
  .kv b{color:var(--mut);font-weight:600}
  .chips span{display:inline-block;background:var(--accent2);color:#1e40af;border-radius:16px;padding:2px 10px;font-size:12px;margin:2px;cursor:pointer}
  .chips span:hover{background:#dbeafe}
  .qcbox{font-size:12.5px;border-radius:8px;padding:6px 10px;margin-top:8px}
  .qcbox.ok{background:#f0fdf4;color:#166534}.qcbox.warn{background:#fffbeb;color:#92400e}
  .txthead{padding:8px 14px;border-bottom:1px solid var(--line);font-weight:600;display:flex;gap:8px;align-items:center;flex-wrap:wrap}
  .txthead .sp{margin-inline-start:auto}
  .txthead button{padding:3px 8px;border:1px solid var(--line);background:var(--pane);border-radius:7px;cursor:pointer;font-size:12px}
  .txt{white-space:pre-wrap;word-break:break-word;padding:12px 15px;font-size:var(--tsize);line-height:var(--tlh);font-family:var(--tfam);text-align:var(--talign);direction:rtl;unicode-bidi:plaintext}
  .distb{display:inline-block;margin-inline-start:6px;background:#fee2e2;color:#b91c1c;border:1px solid #fecaca;border-radius:6px;padding:0 6px;font-size:11px;font-weight:600}
  .num{display:inline-block;min-width:26px;text-align:center;background:var(--chip);color:var(--mut);border-radius:6px;padding:0 5px;font-size:12px;font-weight:700}
  .qb{display:inline-block;border-radius:6px;padding:0 5px;font-size:11px;font-weight:700}
  .txt .ln{display:flex;gap:10px}
  .txt .lno{flex:none;width:38px;color:#9ca3af;text-align:end;user-select:none;display:none}
  body.lines .txt .lno{display:inline-block}
  .txt .lc{flex:1}
  .txt .ln.boiler .lc{opacity:.4;font-style:italic}
  body.hideHdr .txt .ln.boiler{display:none}
  .txt .pgdiv{text-align:center;color:var(--mut);font-size:12px;border-top:1px dashed var(--line);margin:12px 0 6px;padding-top:5px;font-family:Tahoma,Arial}
  .txt .ln.corrected .lc{background:#dcfce7;border-inline-start:3px solid #16a34a;padding-inline-start:6px}
  body.dark .txt .ln.corrected .lc{background:#14532d}
  .corrbanner{background:#ecfdf5;border:1px solid #a7f3d0;color:#065f46;border-radius:8px;padding:7px 10px;font-size:12.5px;margin:8px 0}
  body.dark .corrbanner{background:#064e3b;color:#d1fae5;border-color:#065f46}
  .issbadge{display:inline-block;margin-inline-start:6px;background:#fef3c7;color:#92400e;border:1px solid #fde68a;border-radius:6px;padding:0 6px;font-size:11px}
  mark{background:#fde68a}
  mark.cur{background:#fb923c;color:#000}
  .empty{color:var(--mut);text-align:center;margin-top:60px}
  table{border-collapse:collapse;width:100%;font-size:13px;background:var(--pane)}
  th,td{border:1px solid var(--line);padding:6px 9px;text-align:start;vertical-align:top}
  th{background:var(--accent2);position:sticky;top:0}
  a{color:var(--accent)}
  .modal{position:fixed;inset:0;background:rgba(0,0,0,.35);z-index:20;display:none;align-items:center;justify-content:center}
  .modal.open{display:flex}
  .panel{background:var(--pane);border-radius:14px;padding:18px 20px;width:min(460px,92vw);max-height:88vh;overflow:auto;box-shadow:0 10px 40px rgba(0,0,0,.2)}
  .panel h3{margin:0 0 12px}.panel .opt{margin:8px 0;font-size:14px}
  .panel .acts{display:flex;gap:8px;flex-wrap:wrap;margin-top:14px}
  .panel .acts button{flex:1;min-width:110px;padding:9px;border-radius:9px;border:1px solid var(--accent);background:var(--accent);color:#fff;cursor:pointer;font-size:13px;font-family:inherit}
  .panel .acts button.alt{background:var(--pane);color:var(--accent)}
  .panel .x{float:left;cursor:pointer;color:var(--mut);font-size:18px;border:none;background:none}
  .panel textarea{width:100%;min-height:70px;border:1px solid var(--line);border-radius:8px;padding:8px;font-family:inherit;font-size:13.5px}
  .quote{border:1px solid var(--line);border-radius:8px;padding:8px 10px;margin:6px 0;font-size:13px}
  .quote .src{color:var(--mut);font-size:11.5px;margin-top:4px}
  .selpop{position:absolute;z-index:30;background:#111;color:#fff;border-radius:7px;padding:4px 8px;font-size:12px;cursor:pointer;display:none}
  .bars{display:flex;flex-direction:column;gap:4px;margin:6px 0 14px}
  .bars .b{display:flex;align-items:center;gap:8px;font-size:12px}
  .bars .bar2{height:14px;background:var(--accent);border-radius:3px}
  @media(max-width:760px){.wrap{flex-direction:column;height:auto}.side{width:auto;max-height:46vh}main{height:auto}
    header{flex-wrap:wrap}header h1{font-size:14px}.bar{font-size:11px;gap:4px}.tabs{overflow-x:auto;flex-wrap:nowrap}
    .kv{grid-template-columns:1fr}.txt{font-size:16px}}
</style>
</head>
<body>
<a class="skip" href="#detail">تخطّي إلى محتوى الوثيقة</a>
<header role="banner">
  <h1>واجهة تصفّح القضية</h1>
  <span class="banner">مخرج آلي يحتاج مراجعة بشرية</span>
  <div class="bar" role="toolbar" aria-label="أدوات العرض">
    <span class="grp">نص<button id="fMinus">A−</button><button id="fPlus">A+</button></span>
    <span class="grp">أسطر<button id="lMinus">−</button><button id="lPlus">+</button></span>
    <span class="grp">خط<select id="fFam">
      <option value="'Traditional Arabic','Simplified Arabic','Arabic Typesetting','Amiri',serif" selected>عربي رسمي (نسخ)</option>
      <option value="inherit">افتراضي</option>
      <option value="'Tahoma',Arial,sans-serif">واضح</option>
      <option value="'Courier New',monospace">ثابت</option></select></span>
    <span class="grp"><label><input type="checkbox" id="fJustify" checked> ضبط</label></span>
    <span class="grp"><label><input type="checkbox" id="fReading"> قراءة</label></span>
    <span class="grp">سمة<select id="fTheme"><option value="">فاتح</option><option value="dark">ليلي</option><option value="paper">ورقي</option></select></span>
    <span class="grp"><button id="lockBtn" title="حفظ نسخة مقفلة بكلمة مرور">🔒 قفل</button></span>
    <span class="grp"><button id="loadBtn" title="فتح بيانات قضية أخرى">📂 قضية</button>
      <input type="file" id="loadFile" accept=".js,.json" style="display:none"></span>
  </div>
  <span class="meta" id="meta"></span>
</header>

<div class="tabs">
  <div class="tab active" data-view="docs">المستندات</div>
  <div class="tab" data-view="quotes">المقتطفات</div>
  <div class="tab" data-view="timeline">الخط الزمني</div>
  <div class="tab" data-view="deeds">الصكوك</div>
  <div class="tab" data-view="amounts">المبالغ</div>
  <div class="tab" data-view="grounds">أسباب النقض</div>
  <div class="tab" data-view="laws">الأنظمة</div>
  <div class="tab" data-view="milestones">المحطات</div>
  <div class="tab" data-view="stats">إحصاءات</div>
</div>

<div id="docsView" class="wrap">
  <aside class="side" role="navigation" aria-label="قائمة الوثائق والبحث">
    <div class="controls">
      <label for="q" class="sr-only">بحث في الوثائق</label>
      <input type="text" id="q" aria-label="بحث في الوثائق" placeholder='بحث… (عبارة دقيقة بين "" ، وليس قبل كلمة للاستبعاد)'>
      <div class="row srchopts">
        <label title="يبحث عن كل اشتقاقات الكلمة بنفس الجذر"><input type="checkbox" id="fRoot" checked> جذر</label>
        <label title="تلوين المبالغ/التواريخ/الأطراف/الأرقام"><input type="checkbox" id="fColor" checked> تلوين</label>
        <label title="تحديد الكلمات غير الواضحة (تحتاج مراجعة بشرية)"><input type="checkbox" id="fSusp" checked> غير الواضح</label>
        <label title="إخفاء الترويسات/التذييلات"><input type="checkbox" id="fHideHdr"> إخفاء الترويسات</label>
      </div>
      <div class="row">
        <select id="type" style="flex:1"><option value="">كل الأنواع</option></select>
        <select id="sort" style="flex:1">
          <option value="none">الترتيب: الأصل</option>
          <option value="date">التاريخ</option>
          <option value="title">الأبجدية</option>
          <option value="type">النوع</option></select>
      </div>
      <div class="row">
        <label><input type="checkbox" id="grp"> تجميع حسب النوع</label>
        <label><input type="checkbox" id="onlyFlag"> المعلّمة فقط</label>
        <label title="عرض كل المطابقات عبر الوثائق مع مقتطف"><input type="checkbox" id="fAllRes"> كل النتائج</label>
      </div>
      <div class="row">
        <button id="selAll">تحديد المطابق</button>
        <button id="selNone">إلغاء</button>
        <button id="exportBtn" class="btn-export">تصدير ▾</button>
        <button id="cmpBtn" title="قارن وثيقتين محدّدتين جنباً إلى جنب">⇄ قارن</button>
        <span class="selcount" id="selCount">المحدد: 0</span>
      </div>
      <div class="count" id="count" role="status" aria-live="polite"></div>
    </div>
    <div class="list" id="list" role="list" aria-label="نتائج الوثائق" tabindex="-1"></div>
  </aside>
  <main id="detail" role="main" tabindex="-1"><div class="empty">اختر مستنداً لعرض بطاقته ونصّه الكامل.</div></main>
</div>

<div id="tableView" style="display:none;padding:0 14px 30px"></div>
<div id="quotesView" style="display:none;padding:14px"></div>

<div class="selpop" id="selpop">＋ حفظ كمقتطف</div>

<div class="modal" id="exportModal"><div class="panel">
  <button class="x" id="exportClose">×</button><h3>تصدير المستندات</h3>
  <div class="opt"><b>النطاق:</b><br>
    <label><input type="radio" name="scope" value="selected" checked> المحدد (<span id="scSel">0</span>)</label><br>
    <label><input type="radio" name="scope" value="match"> المطابق (<span id="scMatch">0</span>)</label><br>
    <label><input type="radio" name="scope" value="all"> الكل (<span id="scAll">0</span>)</label></div>
  <div class="opt"><label><input type="checkbox" id="incText" checked> تضمين النص الكامل</label></div>
  <div class="acts">
    <button id="doWord">Word</button><button id="doPrint">طباعة / PDF</button>
    <button id="doHtml" class="alt">HTML</button><button id="doCsv" class="alt">بطاقات CSV</button>
    <button id="doQuotes" class="alt">تصدير المقتطفات/الملاحظات</button></div>
</div></div>

__BOOTSTRAP__
<script>
window.startApp = function(){
  var C=window.CASE||{docs:[],tables:{}}, docs=C.docs||[];
  var LS={get:function(k,d){try{return JSON.parse(localStorage.getItem('cv_'+(C.case_number||'x')+'_'+k))||d;}catch(e){return d;}},
          set:function(k,v){try{localStorage.setItem('cv_'+(C.case_number||'x')+'_'+k,JSON.stringify(v));}catch(e){}}};
  var notes=LS.get('notes',{}), flags=LS.get('flags',{}), quotes=LS.get('quotes',[]), selected={};

  document.getElementById('meta').textContent='القضية '+(C.case_number||'')+' — '+(C.doc_count||docs.length)+' مستند — '+(C.generated||'');

  /* ===== تطبيع عربي + خريطة فهرسة ===== */
  function normChar(ch){
    var c=ch.charCodeAt(0);
    if(c>=0x064B&&c<=0x0652)return '';      // تشكيل
    if(c===0x0640)return '';                 // تطويل
    if(c===0x0670)return '';                 // ألف خنجرية
    if(ch==='أ'||ch==='إ'||ch==='آ'||ch==='ٱ')return 'ا';
    if(ch==='ة')return 'ه';
    if(ch==='ى')return 'ي';
    if(ch==='ؤ')return 'و';
    if(ch==='ئ')return 'ي';
    return ch.toLowerCase();
  }
  function buildNorm(s){var n='',map=[];for(var i=0;i<s.length;i++){var r=normChar(s[i]);if(r){n+=r;map.push(i);}}return {n:n,map:map};}
  function normStr(s){var n='';for(var i=0;i<s.length;i++)n+=normChar(s[i]);return n;}

  /* ===== تحليل استعلام منطقي ===== */
  function parseQuery(q){
    var phrases=[],terms=[],nots=[],orMode=false,i=0;
    var re=/"([^"]+)"|(\S+)/g,m;
    while((m=re.exec(q))){
      if(m[1]!=null){phrases.push(normStr(m[1]));continue;}
      var w=m[2];
      if(w==='أو'||w==='او'||w.toUpperCase()==='OR'){orMode=true;continue;}
      if(w==='و'||w.toUpperCase()==='AND')continue;
      if(w[0]==='-'||w==='ليس'){if(w==='ليس')continue;nots.push(normStr(w.slice(1)));continue;}
      if(w==='ليس'){continue;}
      terms.push(normStr(w));
    }
    return {phrases:phrases,terms:terms,nots:nots,orMode:orMode,empty:(!phrases.length&&!terms.length&&!nots.length)};
  }
  // توسعة الكلمة إلى عائلة جذرها (إن فُعّل «جذر» وتوفّر المعجم MORPH)
  var MORPH=window.MORPH||null;
  var BOILER={};(C.boiler||[]).forEach(function(t){BOILER[t]=1;});
  function rootOn(){var c=document.getElementById('fRoot');return MORPH&&c&&c.checked;}
  function expandTerm(t){
    if(!rootOn())return [t];
    var ids=MORPH.w2r[t];if(!ids)return [t];
    var s={};s[t]=1;for(var i=0;i<ids.length;i++){var a=MORPH.r2w[ids[i]]||[];for(var j=0;j<a.length;j++)s[a[j]]=1;}
    return Object.keys(s);
  }
  function termFamilies(P){return P.terms.map(expandTerm);}
  function matchDoc(P,normHay){
    for(var i=0;i<P.nots.length;i++)if(P.nots[i]&&normHay.indexOf(P.nots[i])>=0)return false;
    var fams=P.phrases.map(function(p){return [p];}).concat(termFamilies(P));
    if(!fams.length)return true;
    function famHit(f){for(var x=0;x<f.length;x++)if(f[x]&&normHay.indexOf(f[x])>=0)return true;return false;}
    if(P.orMode){for(var j=0;j<fams.length;j++)if(famHit(fams[j]))return true;return false;}
    for(var k=0;k<fams.length;k++)if(!famHit(fams[k]))return false;
    return true;
  }
  // ذاكرة مؤقتة للنص المُطبَّع لكل مستند
  docs.forEach(function(d){
    d._h=normStr((d.title||'')+' \n '+(d.full_text||''));
    d._distorted=!!d.distorted; d._distReason=d.distReason||'تشوّه';
  });

  var listEl=document.getElementById('list'),detailEl=document.getElementById('detail'),
      qEl=document.getElementById('q'),countEl=document.getElementById('count'),selCountEl=document.getElementById('selCount');
  var current=null,curP=null,marks=[],markIdx=-1,_pendingPos='first',_pendingMark=null;

  function esc(s){return (s||'').replace(/[&<>]/g,function(c){return{'&':'&amp;','<':'&lt;','>':'&gt;'}[c];});}
  function selectedCount(){var n=0;for(var k in selected)if(selected[k])n++;return n;}
  function updSel(){var n=selectedCount();selCountEl.textContent='المحدد: '+n;document.getElementById('scSel').textContent=n;}

  var typeSel=document.getElementById('type'),sortSel=document.getElementById('sort');
  var types={};docs.forEach(function(d){types[d.doc_type]=(types[d.doc_type]||0)+1;});
  Object.keys(types).sort().forEach(function(t){var o=document.createElement('option');o.value=t;o.textContent=t+' ('+types[t]+')';typeSel.appendChild(o);});

  function dateKey(d){var s=(d.card&&d.card['التاريخ'])||'';var m=s.match(/(\d{2})-(\d{2})-(\d{4})/);return m?(m[3]+m[2]+m[1]):'00000000';}
  function filtered(){
    var P=parseQuery(qEl.value.trim()),t=typeSel.value,of=document.getElementById('onlyFlag').checked;
    var r=docs.filter(function(d){
      if(t&&d.doc_type!==t)return false;
      if(of&&!flags[d.id])return false;
      if(P.empty)return true;
      return matchDoc(P,d._h);
    });
    var s=sortSel.value;
    if(s==='date')r.sort(function(a,b){return dateKey(a).localeCompare(dateKey(b));});
    else if(s==='title')r.sort(function(a,b){return (a.title||'').localeCompare(b.title||'','ar');});
    else if(s==='type')r.sort(function(a,b){return (a.doc_type||'').localeCompare(b.doc_type||'','ar');});
    return r;
  }
  function qcDot(d){var q=d.qc||{};if(!q.status)return '';
    var rev=parseInt(q.rev||'0',10)||0,words=parseInt(q.words||'0',10)||0;
    if(q.status!=='سليم'||rev>3)return '<span class="dot bad" title="نص يحتاج مراجعة"></span>';
    if(rev>0||words<5)return '<span class="dot warn" title="جودة متوسطة"></span>';
    return '<span class="dot ok" title="سليم"></span>';}

  function renderAllResults(fs,P){
    listEl.innerHTML='';var total=0;
    fs.forEach(function(d){
      var occ=occList(d,P);if(!occ.length)return;total+=occ.length;
      var h=document.createElement('div');h.className='grphead';h.textContent=d.title.slice(0,58)+' ('+occ.length+')';
      h.onclick=function(){_pendingMark=0;openDoc(d);};listEl.appendChild(h);
      occ.forEach(function(o){var it=document.createElement('div');it.className='item';
        it.innerHTML='<div class="s" style="font-size:12.5px;line-height:1.75">'+esc(o.pre)+'<mark>'+esc(o.hit)+'</mark>'+esc(o.post)+'</div>';
        it.onclick=function(){_pendingMark=o.i;openDoc(d);};listEl.appendChild(it);});
    });
    countEl.textContent=total+' نتيجة في '+fs.length+' وثيقة';
    if(!total)listEl.innerHTML='<div class="empty" style="margin-top:30px">لا نتائج.</div>';
  }
  function renderList(){
    var fs=filtered();countEl.textContent=(fs.length===docs.length?fs.length+' وثيقة':fs.length+' من '+docs.length+' وثيقة');
    document.getElementById('scMatch').textContent=fs.length;document.getElementById('scAll').textContent=docs.length;
    var _P=parseQuery(qEl.value.trim());var _ar=document.getElementById('fAllRes');
    if(_ar&&_ar.checked&&!_P.empty){renderAllResults(fs,_P);return;}
    listEl.innerHTML='';
    var grouped=document.getElementById('grp').checked;
    function itemEl(d){
      var div=document.createElement('div');div.className='item'+(current&&current.id===d.id?' active':'');
      div.tabIndex=0;div.setAttribute('role','listitem');div.setAttribute('aria-label',(d.n||'')+'. '+d.title+(d.issues?'، جودة '+d.issues.q+' بالمئة':''));
      div.onkeydown=function(ev){
        if(ev.key==='Enter'||ev.key===' '){ev.preventDefault();openDoc(d);}
        else if(ev.key==='ArrowDown'||ev.key==='ArrowUp'){ev.preventDefault();
          var items=listEl.querySelectorAll('.item');var idx=Array.prototype.indexOf.call(items,div);
          var nx=items[idx+(ev.key==='ArrowDown'?1:-1)];if(nx)nx.focus();}};
      var cb=document.createElement('input');cb.type='checkbox';cb.checked=!!selected[d.id];cb.setAttribute('aria-label','تحديد الوثيقة');
      cb.onclick=function(ev){ev.stopPropagation();selected[d.id]=cb.checked;updSel();};
      var body=document.createElement('div');body.style.flex='1';
      var fl=flags[d.id]?' <span class="flag">'+esc(flags[d.id])+'</span>':'';
      var qb=(d.issues&&d.issues.q!=null)?' <span class="qb" style="background:'+(d.issues.q>=85?'#dcfce7;color:#166534':d.issues.q>=70?'#fef9c3;color:#854d0e':'#fee2e2;color:#b91c1c')+'">'+d.issues.q+'%</span>':'';
      body.innerHTML='<div class="t"><span class="num">'+(d.n||'')+'</span> '+(notes[d.id]?'📝 ':'')+esc(d.title)+qcDot(d)+qb+(d._distorted?' <span class="distb" title="'+esc(d._distReason||'تشوّه')+'">⚠ مشوّه</span>':'')+'</div>'+
        '<div class="s">'+esc(d.doc_type)+(d.card&&d.card['التاريخ']?' · '+esc(d.card['التاريخ']):'')+fl+'</div>';
      body.onclick=function(){openDoc(d);};
      div.appendChild(cb);div.appendChild(body);return div;
    }
    if(grouped){
      var by={};fs.forEach(function(d){(by[d.doc_type]=by[d.doc_type]||[]).push(d);});
      Object.keys(by).sort().forEach(function(tp){
        var h=document.createElement('div');h.className='grphead';h.textContent=tp+' ('+by[tp].length+')';
        var wrap=document.createElement('div');
        h.onclick=function(){wrap.style.display=wrap.style.display==='none'?'':'none';};
        listEl.appendChild(h);by[tp].forEach(function(d){wrap.appendChild(itemEl(d));});listEl.appendChild(wrap);
      });
    } else fs.forEach(function(d){listEl.appendChild(itemEl(d));});
    if(!fs.length)listEl.innerHTML='<div class="empty" style="margin-top:30px">لا نتائج.</div>';
  }

  /* ===== تحويل التاريخ هجري/ميلادي (تقريبي تبويبي) ===== */
  function gregToJD(y,m,d){var a=Math.floor((14-m)/12),yy=y+4800-a,mm=m+12*a-3;
    return d+Math.floor((153*mm+2)/5)+365*yy+Math.floor(yy/4)-Math.floor(yy/100)+Math.floor(yy/400)-32045;}
  function jdToGreg(jd){var a=jd+32044,b=Math.floor((4*a+3)/146097),c=a-Math.floor(146097*b/4),
    dd=Math.floor((4*c+3)/1461),e=c-Math.floor(1461*dd/4),mm=Math.floor((5*e+2)/153);
    var day=e-Math.floor((153*mm+2)/5)+1,month=mm+3-12*Math.floor(mm/10),year=100*b+dd-4800+Math.floor(mm/10);
    return [year,month,day];}
  function hijriToJD(y,m,d){return d+Math.ceil(29.5*(m-1))+(y-1)*354+Math.floor((3+11*y)/30)+1948440-385;}
  function jdToHijri(jd){var y=Math.floor((30*(jd-1948440+385)+10646)/10631);
    var m=Math.min(12,Math.ceil((jd-(29+hijriToJD(y,1,1)-1))/29.5)+1);if(m<1)m=1;
    var d=jd-hijriToJD(y,m,1)+1;return [y,m,d];}
  function pad(n){return (n<10?'0':'')+n;}
  function convertDate(s){var m=String(s).match(/(\d{1,2})-(\d{1,2})-(\d{3,4})/);if(!m)return '';
    var d=+m[1],mo=+m[2],y=+m[3];
    try{if(y<1700){var g=jdToGreg(hijriToJD(y,mo,d));return 'م '+pad(g[2])+'-'+pad(g[1])+'-'+g[0]+' (تقريبي)';}
      else{var h=jdToHijri(gregToJD(y,mo,d));return 'هـ '+pad(h[2])+'-'+pad(h[1])+'-'+h[0]+' (تقريبي)';}}catch(e){return '';}}

  function chips(arr,kind){if(!arr||!arr.length)return '';
    return '<div class="chips">'+arr.map(function(x){return '<span data-q="'+esc(x)+'">'+esc(x)+'</span>';}).join('')+'</div>';}

  function openDoc(d){
    current=d;curP=parseQuery(qEl.value.trim());
    var card=d.card||{},e=d.entities||{},kv='';
    Object.keys(card).forEach(function(k){if(card[k]){var conv=(k==='التاريخ')?convertDate(card[k]):'';
      kv+='<b>'+esc(k)+'</b><div>'+esc(card[k])+(conv?' <span style="color:var(--mut);font-size:12px">— '+esc(conv)+'</span>':'')+'</div>';}});
    var ent='';
    function rowE(label,arr){if(arr&&arr.length)ent+='<div style="margin-top:6px"><b style="color:var(--mut)">'+label+':</b>'+chips(arr)+'</div>';}
    rowE('الأطراف',e.parties);rowE('أطراف آخرون',e.other_actors);rowE('الشركة',e.company);
    rowE('أرقام القضايا',e.case_numbers);rowE('أرقام الصكوك',e.deed_numbers_known);
    rowE('تواريخ هجرية',e.hijri_dates);rowE('تواريخ ميلادية',e.greg_dates);
    rowE('مبالغ',e.amounts);rowE('محاكم',e.courts);rowE('أنظمة',e.law_names);rowE('مواد',e.articles);
    var q=d.qc||{},qcHtml='';
    if(q.status){var rev=parseInt(q.rev||'0',10)||0,bad=(q.status!=='سليم'||rev>3);
      qcHtml='<div class="qcbox '+(bad?'warn':'ok')+'">جودة القراءة: '+esc(q.status)+
        ' · أسطر معكوسة متبقية: '+esc(q.rev||'0')+' · كلمات: '+esc(q.words||'0')+
        (bad?' — ⚠ يُنصح بمراجعة النص الأصلي':'')+'</div>';}
    var fl=flags[d.id]||'';
    detailEl.innerHTML=
      '<div class="card"><h2>'+esc(d.title)+'</h2><div class="kv">'+kv+'</div>'+
        (d.corr&&d.corr.length?'<div class="corrbanner">⚙ عُدِّل آلياً '+d.corr.length+' سطر (كان معكوس الاتجاه) بناءً على الملف المصدر — بمعالج آلي. الأسطر الخضراء في النص هي المُعدَّلة؛ مرّر الفأرة عليها لرؤية الأصل.</div>':'')+
        (d.issues?'<div class="kv" style="margin-top:6px">🔎 كشّاف الأخطاء — جودة القراءة: <b>'+(d.issues.q!=null?d.issues.q+'%':'-')+'</b> · عكس اتجاه: '+d.issues.rev+' · أسطر ترويسة: '+d.issues.hdr+' · كلمات غير واضحة: '+d.issues.unclear+(d.issues.badsym?' · رموز تالفة: '+d.issues.badsym:'')+(d.issues.q!=null&&d.issues.q<70?' · <b style="color:#b91c1c">يُنصح بإعادة OCR</b>':'')+'</div>':'')+
        (d.parent_path?'<div style="margin-top:8px;color:var(--mut);font-size:12px">المسار: '+esc(d.parent_path)+'</div>':'')+
        (d.viewUrl?'<div style="margin-top:6px"><a class="openlink" href="'+esc(d.viewUrl)+'" target="_blank">فتح الأصل في Drive ↗</a></div>':'')+
        ent+qcHtml+
        '<div style="margin-top:10px;display:flex;gap:6px;flex-wrap:wrap">'+
          '<button class="qbtn" data-a="ask">🤖 جهّز سؤالاً لكلود</button>'+
          '<button class="qbtn" data-a="copy">📋 نسخ النص</button>'+
          '<select id="flagSel"><option value="">— علم —</option>'+
            ['مهم','روجع','يحتاج مراجعة'].map(function(x){return '<option'+(fl===x?' selected':'')+'>'+x+'</option>';}).join('')+
          '</select>'+
          '<button class="qbtn" data-a="note">📝 ملاحظة</button>'+
        '</div>'+
        (notes[d.id]?'<div style="margin-top:8px;background:#fffef0;border:1px solid var(--line);border-radius:8px;padding:8px;font-size:13px">📝 '+esc(notes[d.id])+'</div>':'')+
      '</div>'+
      '<div class="card" style="padding:0"><div class="txthead">النص الكامل'+
        (d._distorted?'<span class="distb" title="مخرج آلي قد يحتاج إعادة قراءة">⚠ مشوّه — '+esc(d._distReason||'')+'</span>':'')+
        '<span class="sp"></span>'+
        '<button id="mPrev" aria-label="المطابقة السابقة">▲</button><span id="mInfo" role="status" aria-live="polite" style="font-size:12px;color:var(--mut)">—</span><button id="mNext" aria-label="المطابقة التالية">▼</button>'+
        '<button id="lnToggle" aria-label="إظهار/إخفاء أرقام الأسطر">#أسطر</button></div>'+
        '<div class="txt" id="txtBox"></div></div>';
    renderText(d,curP);
    detailEl.scrollTop=0;highlightList();bindDetail(d);
  }

  function reEsc(s){return s.replace(/[.*+?^${}()|[\]\\]/g,'\\$&');}
  function makeColorizer(d){
    var col=document.getElementById('fColor'),colOn=!col||col.checked;
    var sc=document.getElementById('fSusp'),suspOn=!sc||sc.checked;
    var SS=(window.SUSPECT&&window.SUSPECT[d.id])?window.SUSPECT[d.id]:null;
    var suspSet=null;if(SS&&suspOn){suspSet={};for(var z=0;z<SS.length;z++)suspSet[SS[z]]=1;}
    if(!colOn&&!suspSet)return function(s){return s;};
    var e=d.entities||{};
    var names=colOn?[].concat(e.parties||[],e.other_actors||[],e.company||[]).filter(Boolean)
              .map(function(x){return reEsc(esc(x));}).sort(function(a,b){return b.length-a.length;}):[];
    var nameAlt=names.length?names.join('|'):'(?!)';
    var re=new RegExp('('+nameAlt+')'
      +'|((?:[٠-٩]|\\d)[٠-٩\\d.,٬]*\\s*(?:ريال|ر\\.?س|مليون|مليار|ألف|الف|﷼))'
      +'|(\\d{1,2}\\s*[\\/\\-]\\s*\\d{1,2}\\s*[\\/\\-]\\s*\\d{2,4}|\\d{3,4}\\s*هـ|\\d{4}\\s*م)'
      +'|((?:[٠-٩]|\\d){6,})'
      +'|([ء-ي]{2,})','g');
    return function(s){return s.replace(re,function(m,a,b,c2,d2,w){
      if(w!==undefined&&w!==''){ // كلمة عربية: علّمها إن كانت مشتبهة
        if(suspSet&&suspSet[normStr(w)])return '<u class="susp" title="كلمة غير واضحة — تحتاج مراجعة">'+m+'</u>';
        return m;
      }
      if(!colOn)return m;
      return '<span class="e-'+(a?'party':b?'amt':c2?'date':'num')+'">'+m+'</span>';});};
  }
  function renderText(d,P){
    var box=document.getElementById('txtBox');var text=d.full_text||'(لا يوجد نص مستخرج)';var colorize=makeColorizer(d);
    var pos=[];if(P){pos=P.phrases.slice();P.terms.forEach(function(t){pos=pos.concat(expandTerm(t));});pos=pos.filter(Boolean);}
    var nb=buildNorm(text);var n=nb.n,map=nb.map;
    var hits=[];
    pos.forEach(function(term){if(!term)return;var idx=0;while((idx=n.indexOf(term,idx))>=0){hits.push([idx,idx+term.length]);idx+=term.length;}});
    hits.sort(function(a,b){return a[0]-b[0];});
    // ادمج المتداخل
    var merged=[];hits.forEach(function(h){if(merged.length&&h[0]<=merged[merged.length-1][1])merged[merged.length-1][1]=Math.max(merged[merged.length-1][1],h[1]);else merged.push(h);});
    // ابنِ نصاً مظللاً بمواضع أصلية
    var out='',oi=0,mi=0;
    function origIdx(np){return np<map.length?map[np]:(map.length?map[map.length-1]+1:0);}
    var ranges=merged.map(function(h){return [origIdx(h[0]),origIdx(h[1]-1)+1];});
    var k=0;
    for(var c=0;c<text.length;){
      if(k<ranges.length&&c===ranges[k][0]){
        out+='<mark>'+esc(text.slice(ranges[k][0],ranges[k][1]))+'</mark>';c=ranges[k][1];k++;
      } else {var nextStart=k<ranges.length?ranges[k][0]:text.length;out+=colorize(esc(text.slice(c,nextStart)));c=nextStart;}
    }
    // ترقيم أسطر
    var lines=out.split('\n');var rawLines=text.split('\n');
    var hdrSet={};(d.hdr||[]).forEach(function(x){hdrSet[x]=1;});
    var corrMap={};(d.corr||[]).forEach(function(c){corrMap[c.i]=c.o;});
    box.innerHTML=lines.map(function(l,i){
      var raw=(rawLines[i]||'').trim();
      if(/^\[\s*صفح[ةه]\s*\d+\s*\]/.test(raw))return '<div class="pgdiv">'+esc(raw.replace(/^\[\s*|\s*\]$/g,''))+'</div>';
      var bl=(BOILER[normStr(raw)]||hdrSet[i])?' boiler':'';
      var cc=corrMap.hasOwnProperty(i)?' corrected':'';
      var ti=corrMap.hasOwnProperty(i)?' title="مُعدَّل آلياً (كان معكوس الاتجاه) بناءً على الملف المصدر — معالج آلي. الأصل: '+esc(String(corrMap[i]).slice(0,80)).replace(/"/g,"”")+'"':'';
      return '<div class="ln'+bl+cc+'"'+ti+'><span class="lno">'+(i+1)+'</span><span class="lc">'+l+'</span></div>';}).join('');
    marks=Array.prototype.slice.call(box.querySelectorAll('mark'));markIdx=marks.length?0:-1;updMarkInfo();
    if(marks.length){var tgt=(_pendingMark!=null&&_pendingMark<marks.length)?_pendingMark:(_pendingPos==='last'?marks.length-1:0);gotoMark(tgt);}
    _pendingPos='first';_pendingMark=null;
  }
  // مواضع المطابقات لوثيقة (للوحة كل النتائج) — بنفس منطق التظليل
  function posOf(P){var pos=[];if(P){pos=P.phrases.slice();P.terms.forEach(function(t){pos=pos.concat(expandTerm(t));});pos=pos.filter(Boolean);}return pos;}
  function rangesOf(text,pos){
    var nb=buildNorm(text),n=nb.n,map=nb.map,hits=[];
    pos.forEach(function(term){if(!term)return;var idx=0;while((idx=n.indexOf(term,idx))>=0){hits.push([idx,idx+term.length]);idx+=term.length;}});
    hits.sort(function(a,b){return a[0]-b[0];});
    var merged=[];hits.forEach(function(h){if(merged.length&&h[0]<=merged[merged.length-1][1])merged[merged.length-1][1]=Math.max(merged[merged.length-1][1],h[1]);else merged.push(h);});
    function oi(np){return np<map.length?map[np]:(map.length?map[map.length-1]+1:0);}
    return merged.map(function(h){return [oi(h[0]),oi(h[1]-1)+1];});
  }
  function occList(d,P){var pos=posOf(P);if(!pos.length)return [];var t=d.full_text||'';
    return rangesOf(t,pos).map(function(rg,i){var a=Math.max(0,rg[0]-32),b=Math.min(t.length,rg[1]+40);
      return {i:i,pre:(a>0?'…':'')+t.slice(a,rg[0]),hit:t.slice(rg[0],rg[1]),post:t.slice(rg[1],b)+(b<t.length?'…':'')};});}
  function updMarkInfo(){var el=document.getElementById('mInfo');if(!el)return;
    var P=parseQuery(qEl.value.trim());var fl=P.empty?[]:filtered();
    var di=-1;for(var z=0;z<fl.length;z++){if(current&&fl[z].id===current.id){di=z;break;}}
    var dp=(fl.length>1&&di>=0)?(' · وثيقة '+(di+1)+'/'+fl.length):'';
    el.textContent=marks.length?((markIdx+1)+' من '+marks.length+dp):(fl.length>1&&di>=0?('وثيقة '+(di+1)+'/'+fl.length):'—');}
  function gotoMark(i){if(!marks.length)return;markIdx=(i+marks.length)%marks.length;
    marks.forEach(function(m){m.classList.remove('cur');});marks[markIdx].classList.add('cur');
    marks[markIdx].scrollIntoView({block:'center'});updMarkInfo();}
  // تنقّل مثل Word: بين المطابقات داخل الوثيقة، ثم يعبر إلى الوثيقة المطابقة التالية/السابقة.
  function _matchDocs(){var P=parseQuery(qEl.value.trim());return P.empty?[]:filtered();}
  function _curIdxIn(fl){for(var z=0;z<fl.length;z++){if(current&&fl[z].id===current.id)return z;}return -1;}
  function navNext(){
    if(marks.length&&markIdx<marks.length-1){gotoMark(markIdx+1);return;}
    var fl=_matchDocs();if(fl.length<2){if(marks.length)gotoMark(0);return;}
    var i=_curIdxIn(fl);_pendingPos='first';openDoc(fl[(i+1+fl.length)%fl.length]);}
  function navPrev(){
    if(marks.length&&markIdx>0){gotoMark(markIdx-1);return;}
    var fl=_matchDocs();if(fl.length<2){if(marks.length)gotoMark(marks.length-1);return;}
    var i=_curIdxIn(fl);_pendingPos='last';openDoc(fl[(i-1+fl.length)%fl.length]);}

  function bindDetail(d){
    var p=document.getElementById('mPrev'),n=document.getElementById('mNext');
    if(p)p.onclick=function(){navPrev();};if(n)n.onclick=function(){navNext();};
    var lt=document.getElementById('lnToggle');if(lt)lt.onclick=function(){document.body.classList.toggle('lines');};
    detailEl.querySelectorAll('.chips span').forEach(function(s){s.onclick=function(){qEl.value='"'+s.getAttribute('data-q')+'"';renderList();openDoc(current);};});
    detailEl.querySelectorAll('.qbtn').forEach(function(b){b.onclick=function(){
      var a=b.getAttribute('data-a');
      if(a==='copy'){navigator.clipboard&&navigator.clipboard.writeText(d.full_text||'');b.textContent='✓ نُسخ';setTimeout(function(){b.textContent='📋 نسخ النص';},1200);}
      else if(a==='ask'){var prompt='حلّل المستند التالي من قضية '+(C.case_number||'')+'. المطلوب: لخّصه، واستخرج الطلبات والأسانيد، وأبرز أي مخاطر. تذكير: مساعدة آلية تحتاج مراجعة قانونية.\\n\\nالعنوان: '+d.title+'\\n\\nالنص:\\n'+(d.full_text||'');
        navigator.clipboard&&navigator.clipboard.writeText(prompt);b.textContent='✓ انسخه في كلود';setTimeout(function(){b.textContent='🤖 جهّز سؤالاً لكلود';},1500);}
      else if(a==='note'){var v=window.prompt('ملاحظتك على هذا المستند:',notes[d.id]||'');if(v!==null){if(v)notes[d.id]=v;else delete notes[d.id];LS.set('notes',notes);openDoc(d);renderList();}}
    };});
    var fs=document.getElementById('flagSel');if(fs)fs.onchange=function(){var v=fs.value;if(v)flags[d.id]=v;else delete flags[d.id];LS.set('flags',flags);renderList();};
  }
  function highlightList(){listEl.querySelectorAll('.item').forEach(function(el){el.classList.remove('active');});}

  /* ===== تحديد المقتطف ===== */
  var selpop=document.getElementById('selpop');
  document.addEventListener('mouseup',function(){
    var sel=window.getSelection(),txt=sel&&sel.toString().trim();
    if(txt&&txt.length>1&&current&&detailEl.contains(sel.anchorNode)){
      var rc=sel.getRangeAt(0).getBoundingClientRect();
      selpop.style.top=(window.scrollY+rc.top-32)+'px';selpop.style.left=(window.scrollX+rc.left)+'px';
      selpop.style.display='block';selpop._txt=txt;
    } else selpop.style.display='none';
  });
  selpop.onclick=function(){if(selpop._txt&&current){quotes.push({t:selpop._txt,id:current.id,title:current.title,date:new Date().toISOString().slice(0,10)});LS.set('quotes',quotes);selpop.style.display='none';if(curView==='quotes')renderQuotes();}};

  var qt;qEl.oninput=function(){clearTimeout(qt);qt=setTimeout(function(){renderList();
    var P=parseQuery(qEl.value.trim());
    if(!P.empty){var fl=filtered();if(fl.length){if(!current||!matchDoc(P,current._h)){_pendingPos='first';openDoc(fl[0]);}else openDoc(current);}}
    else if(current)openDoc(current);
  },160);};
  // Enter = النتيجة التالية، Shift+Enter = السابقة (مثل Word)
  qEl.onkeydown=function(e){if(e.key==='Enter'){e.preventDefault();if(e.shiftKey)navPrev();else navNext();}};
  typeSel.onchange=renderList;sortSel.onchange=renderList;
  var fr=document.getElementById('fRoot');if(fr)fr.onchange=function(){renderList();if(current)openDoc(current);};
  document.getElementById('grp').onchange=renderList;document.getElementById('onlyFlag').onchange=renderList;
  document.getElementById('fAllRes').onchange=renderList;
  var hh=document.getElementById('fHideHdr');if(hh)hh.onchange=function(){document.body.classList.toggle('hideHdr',this.checked);if(current)openDoc(current);};
  var fc=document.getElementById('fColor');if(fc)fc.onchange=function(){if(current)openDoc(current);};
  var fsp=document.getElementById('fSusp');if(fsp)fsp.onchange=function(){if(current)openDoc(current);};
  var ft=document.getElementById('fTheme');
  function applyTheme(v){document.body.classList.remove('dark','paper');if(v)document.body.classList.add(v);}
  if(ft){var svt=LS.get('theme','');ft.value=svt;applyTheme(svt);ft.onchange=function(){applyTheme(ft.value);LS.set('theme',ft.value);};}
  var cmp=document.getElementById('cmpBtn');if(cmp)cmp.onclick=function(){
    var ids=Object.keys(selected).filter(function(k){return selected[k];});
    if(ids.length!==2){alert('حدّد وثيقتين بالضبط للمقارنة.');return;}
    var pair=ids.map(function(id){return docs.filter(function(d){return d.id===id;})[0];}).filter(Boolean);
    if(pair.length!==2)return;
    function col(d){var cz=makeColorizer(d);
      return '<div style="flex:1;min-width:0;border:1px solid var(--line);border-radius:8px;overflow:hidden">'+
        '<div class="txthead">'+esc(d.title.slice(0,60))+'</div>'+
        '<div class="txt" style="max-height:74vh;overflow:auto">'+cz(esc(d.full_text||'(لا نص)')) +'</div></div>';}
    detailEl.innerHTML='<div style="display:flex;gap:10px;padding:8px">'+col(pair[0])+col(pair[1])+'</div>';
  };
  document.getElementById('selAll').onclick=function(){filtered().forEach(function(d){selected[d.id]=true;});updSel();renderList();};
  document.getElementById('selNone').onclick=function(){selected={};updSel();renderList();};
  renderList();updSel();

  /* ===== الخط (محفوظ) ===== */
  var FS=18,LH=1.9;
  function applyFont(){var r=document.documentElement.style;r.setProperty('--tsize',FS+'px');r.setProperty('--tlh',LH);
    r.setProperty('--tfam',document.getElementById('fFam').value);
    r.setProperty('--talign',document.getElementById('fJustify').checked?'justify':'start');
    LS.set('font',{FS:FS,LH:LH,fam:document.getElementById('fFam').value,j:document.getElementById('fJustify').checked});}
  var sv=LS.get('font',null);if(sv){FS=sv.FS||FS;LH=sv.LH||LH;document.getElementById('fFam').value=sv.fam||'inherit';document.getElementById('fJustify').checked=!!sv.j;}
  document.getElementById('fPlus').onclick=function(){FS=Math.min(28,FS+1);applyFont();};
  document.getElementById('fMinus').onclick=function(){FS=Math.max(11,FS-1);applyFont();};
  document.getElementById('lPlus').onclick=function(){LH=Math.min(2.6,Math.round((LH+0.1)*10)/10);applyFont();};
  document.getElementById('lMinus').onclick=function(){LH=Math.max(1.2,Math.round((LH-0.1)*10)/10);applyFont();};
  document.getElementById('fFam').onchange=applyFont;document.getElementById('fJustify').onchange=applyFont;
  document.getElementById('fReading').onchange=function(){document.body.classList.toggle('reading',this.checked);};
  applyFont();

  /* ===== اختصارات ===== */
  document.addEventListener('keydown',function(e){
    if(/INPUT|TEXTAREA|SELECT/.test((e.target.tagName||'')))return;
    if(e.key==='/'){e.preventDefault();qEl.focus();}
    else if(e.key==='n'){gotoMark(markIdx+1);}else if(e.key==='N'){gotoMark(markIdx-1);}
    else if(e.key==='r'){var rc=document.getElementById('fReading');rc.checked=!rc.checked;document.body.classList.toggle('reading',rc.checked);}
    else if(e.key==='j'||e.key==='k'){var fs=filtered();if(!fs.length)return;var i=current?fs.findIndex(function(d){return d.id===current.id;}):-1;
      i=e.key==='j'?Math.min(fs.length-1,i+1):Math.max(0,i-1);if(fs[i])openDoc(fs[i]);}
  });

  /* ===== التصدير ===== */
  var modal=document.getElementById('exportModal');
  document.getElementById('exportBtn').onclick=function(){updSel();modal.classList.add('open');};
  document.getElementById('exportClose').onclick=function(){modal.classList.remove('open');};
  modal.onclick=function(e){if(e.target===modal)modal.classList.remove('open');};
  function scopeDocs(){var s=document.querySelector('input[name=scope]:checked').value;
    return s==='all'?docs:s==='match'?filtered():docs.filter(function(d){return selected[d.id];});}
  function dl(name,content,mime){var b=new Blob([content],{type:mime}),u=URL.createObjectURL(b),a=document.createElement('a');
    a.href=u;a.download=name;document.body.appendChild(a);a.click();document.body.removeChild(a);setTimeout(function(){URL.revokeObjectURL(u);},1500);}
  function csvCell(s){return '"'+String(s==null?'':s).replace(/"/g,'""')+'"';}
  function buildHTML(list,incText,word){
    var ns=word?'<html xmlns:o="urn:schemas-microsoft-com:office:office" xmlns:w="urn:schemas-microsoft-com:office:word" xmlns="http://www.w3.org/TR/REC-html40">':'<!DOCTYPE html><html lang="ar" dir="rtl">';
    var p=[ns,'<head><meta http-equiv="Content-Type" content="text/html; charset=utf-8"><title>مستندات القضية</title>',
      word?'<!--[if gte mso 9]><xml><w:WordDocument><w:View>Print</w:View></w:WordDocument></xml><![endif]-->':'',
      '<style>body{font-family:Tahoma,Arial,sans-serif;color:#111;margin:24px;line-height:1.8;direction:rtl;text-align:right}',
      'h2{font-size:15px;margin:0 0 6px}table{border-collapse:collapse;margin:6px 0}td,th{border:1px solid #ccc;padding:4px 8px;font-size:12px;text-align:right}th{background:#eef}',
      '.txt{white-space:pre-wrap;word-break:break-word;font-size:12.5px;border-top:1px solid #eee;margin-top:8px;padding-top:8px}',
      '.doc+.doc{page-break-before:always}.note{color:#7c2d12}a{color:#1d4ed8}@media print{.noprint{display:none}}</style></head><body dir="rtl" lang="ar">',
      word?'':'<div class="noprint" style="margin-bottom:10px"><button onclick="window.print()" style="padding:8px 16px;cursor:pointer">🖨️ اطبع / احفظ PDF</button></div>',
      '<h1 style="font-size:18px">مستندات القضية '+esc(C.case_number||'')+' — عدد: '+list.length+'</h1>',
      '<p class="note">مخرج آلي يحتاج مراجعة بشرية · '+esc(C.generated||'')+'</p>'];
    list.forEach(function(d,i){var card=d.card||{},kv='';
      Object.keys(card).forEach(function(k){if(card[k])kv+='<tr><th>'+esc(k)+'</th><td>'+esc(card[k])+'</td></tr>';});
      p.push('<div class="doc"'+(word&&i>0?' style="page-break-before:always"':'')+'><h2>'+esc(d.title)+'</h2>');
      p.push('<div style="color:#666;font-size:11px">'+esc(d.doc_type)+(d.parent_path?' · '+esc(d.parent_path):'')+'</div>');
      if(kv)p.push('<table>'+kv+'</table>');
      if(d.viewUrl)p.push('<div><a href="'+esc(d.viewUrl)+'">الرابط السحابي ↗</a></div>');
      if(incText)p.push('<div class="txt">'+esc(d.full_text||'(لا نص)')+'</div>');p.push('</div>');});
    p.push('</body></html>');return p.join('');}
  document.getElementById('doPrint').onclick=function(){var l=scopeDocs();if(!l.length){alert('لا مستندات.');return;}
    var w=window.open('','_blank');if(!w){alert('اسمح بالنوافذ المنبثقة أو استخدم تنزيل HTML.');return;}
    w.document.open();w.document.write(buildHTML(l,document.getElementById('incText').checked,false));w.document.close();modal.classList.remove('open');};
  document.getElementById('doHtml').onclick=function(){var l=scopeDocs();if(!l.length){alert('لا مستندات.');return;}
    dl('مستندات_القضية.html',buildHTML(l,document.getElementById('incText').checked,false),'text/html;charset=utf-8');modal.classList.remove('open');};
  document.getElementById('doWord').onclick=function(){var l=scopeDocs();if(!l.length){alert('لا مستندات.');return;}
    dl('مستندات_القضية.doc',buildHTML(l,document.getElementById('incText').checked,true),'application/msword');modal.classList.remove('open');};
  document.getElementById('doCsv').onclick=function(){var l=scopeDocs();if(!l.length){alert('لا مستندات.');return;}
    var head=['العنوان','النوع','التاريخ','الأطراف','الجهة','رقم القضية','رقم الصك','العلم','ملاحظة','المسار','الرابط السحابي'];
    var lines=['﻿'+head.map(csvCell).join(',')];
    l.forEach(function(d){var c=d.card||{};lines.push([d.title,d.doc_type,c['التاريخ']||'',c['الأطراف']||'',c['الجهة المصدِرة']||c['الجهة']||'',
      c['رقم القضية']||'',c['رقم الصك/الحكم']||c['رقم الصك']||'',flags[d.id]||'',notes[d.id]||'',d.parent_path||'',d.viewUrl||''].map(csvCell).join(','));});
    dl('بطاقات_القضية.csv',lines.join('\r\n'),'text/csv;charset=utf-8');modal.classList.remove('open');};
  document.getElementById('doQuotes').onclick=function(){exportQuotes();modal.classList.remove('open');};
  function exportQuotes(){
    var head=['نوع','النص','المستند','التاريخ'],lines=['﻿'+head.map(csvCell).join(',')];
    quotes.forEach(function(q){lines.push(['مقتطف',q.t,q.title,q.date].map(csvCell).join(','));});
    Object.keys(notes).forEach(function(id){var d=docs.filter(function(x){return x.id===id;})[0];lines.push(['ملاحظة',notes[id],d?d.title:id,''].map(csvCell).join(','));});
    Object.keys(flags).forEach(function(id){var d=docs.filter(function(x){return x.id===id;})[0];lines.push(['علم: '+flags[id],'',d?d.title:id,''].map(csvCell).join(','));});
    dl('مقتطفات_وملاحظات_القضية.csv',lines.join('\r\n'),'text/csv;charset=utf-8');}

  /* ===== المقتطفات (تبويب) ===== */
  function renderQuotes(){var v=document.getElementById('quotesView');
    var h='<h3>المقتطفات والملاحظات</h3><div style="margin-bottom:8px"><button id="expQ" style="padding:6px 12px;cursor:pointer">تصدير CSV</button></div>';
    if(!quotes.length&&!Object.keys(notes).length)h+='<div class="empty">لا مقتطفات بعد. حدّد نصاً داخل أي مستند ثم اضغط «حفظ كمقتطف».</div>';
    quotes.forEach(function(q,i){h+='<div class="quote">«'+esc(q.t)+'»<div class="src">— '+esc(q.title)+' · '+esc(q.date)+' <a href="#" data-del="'+i+'">حذف</a></div></div>';});
    Object.keys(notes).forEach(function(id){var d=docs.filter(function(x){return x.id===id;})[0];h+='<div class="quote">📝 '+esc(notes[id])+'<div class="src">— '+esc(d?d.title:id)+'</div></div>';});
    v.innerHTML=h;
    var e=document.getElementById('expQ');if(e)e.onclick=exportQuotes;
    v.querySelectorAll('[data-del]').forEach(function(a){a.onclick=function(ev){ev.preventDefault();quotes.splice(+a.getAttribute('data-del'),1);LS.set('quotes',quotes);renderQuotes();};});}

  /* ===== الجداول + الرسوم ===== */
  var tableView=document.getElementById('tableView'),docsView=document.getElementById('docsView'),quotesView=document.getElementById('quotesView'),curView='docs';
  function amountsChart(t){var idxV=t.header.findIndex(function(h){return /قيمة|مبلغ/.test(h);});if(idxV<0)idxV=0;
    var rows=t.rows.slice(0,12).map(function(r){var num=parseFloat(String(r[idxV]).replace(/[^\d.]/g,''))||0;return {label:r[idxV],v:num};});
    var max=Math.max.apply(null,rows.map(function(x){return x.v;}))||1;
    return '<div class="bars">'+rows.map(function(x){return '<div class="b"><span style="width:120px">'+esc(x.label)+'</span><span class="bar2" style="width:'+(Math.max(2,260*x.v/max))+'px"></span></div>';}).join('')+'</div>';}
  function renderStats(){
    function group(fn){var m={};docs.forEach(function(d){var k=fn(d)||'—';m[k]=(m[k]||0)+1;});return m;}
    function bars(title,m,onClick){
      var keys=Object.keys(m).sort(function(a,b){return m[b]-m[a];});var mx=Math.max.apply(null,keys.map(function(k){return m[k];}))||1;
      return '<h3>'+title+'</h3>'+keys.map(function(k){var id=onClick?(' data-k="'+esc(k)+'"'):'';
        return '<div class="sbar"><span class="lbl"'+(onClick?' style="text-decoration:underline dotted"':'')+id+'>'+esc(k)+'</span>'+
          '<span class="bb" style="width:'+Math.max(3,260*m[k]/mx)+'px"></span><span class="cnt">'+m[k]+'</span></div>';}).join('');}
    function yearOf(d){var s=(d.card&&d.card['التاريخ'])||'';var m=s.match(/(1[34]\d\d)|((?:19|20)\d\d)/);return m?m[0]:'بدون تاريخ';}
    function qualOf(d){if(d._distorted)return 'مشوّه';var q=(d.qc||{}).status;return q||'غير مقيّم';}
    var html='<div class="statwrap">'+
      bars('حسب النوع ('+docs.length+' وثيقة) — اضغط للتصفية',group(function(d){return d.doc_type;}),true)+
      bars('حسب السنة',group(yearOf),false)+
      bars('حسب الجودة',group(qualOf),false)+'</div>';
    tableView.innerHTML=html;
    tableView.querySelectorAll('.sbar .lbl[data-k]').forEach(function(el){el.onclick=function(){
      typeSel.value=el.getAttribute('data-k');
      document.querySelectorAll('.tab').forEach(function(x){x.classList.remove('active');});
      document.querySelector('.tab[data-view="docs"]').classList.add('active');curView='docs';
      docsView.style.display='';tableView.style.display='none';quotesView.style.display='none';renderList();};});
  }
  function showTable(key){
    if(key==='stats'){renderStats();return;}
    var t=(C.tables||{})[key];
    if(!t){tableView.innerHTML='<div class="empty" style="margin-top:40px">لا جدول.</div>';return;}
    var extra='';if(key==='amounts')extra='<h4>أكبر المبالغ (رسم)</h4>'+amountsChart(t);
    var h=extra+'<table><thead><tr>'+t.header.map(function(x){return '<th>'+esc(x)+'</th>';}).join('')+'</tr></thead><tbody>';
    t.rows.forEach(function(r){h+='<tr>'+r.map(function(x){return '<td>'+esc(x)+'</td>';}).join('')+'</tr>';});
    tableView.innerHTML=h+'</tbody></table>';}
  document.querySelectorAll('.tab').forEach(function(tab){
    tab.tabIndex=0;tab.setAttribute('role','tab');
    tab.onkeydown=function(e){if(e.key==='Enter'||e.key===' '){e.preventDefault();tab.click();}};
    tab.onclick=function(){
    document.querySelectorAll('.tab').forEach(function(x){x.classList.remove('active');});tab.classList.add('active');
    var v=tab.getAttribute('data-view');curView=v;
    docsView.style.display=v==='docs'?'':'none';
    quotesView.style.display=v==='quotes'?'':'none';
    tableView.style.display=(v!=='docs'&&v!=='quotes')?'':'none';
    if(v==='quotes')renderQuotes();else if(v!=='docs')showTable(v);};});

  /* ===== تعدّد القضايا ===== */
  document.getElementById('loadBtn').onclick=function(){document.getElementById('loadFile').click();};
  document.getElementById('loadFile').onchange=function(ev){var f=ev.target.files[0];if(!f)return;var r=new FileReader();
    r.onload=function(){try{var txt=r.result,m=txt.indexOf('{');var obj=JSON.parse(txt.slice(m,txt.lastIndexOf('}')+1));
      if(!obj.docs)throw 0;window.CASE=obj;document.getElementById('tableView').innerHTML='';window.startApp();
    }catch(e){alert('ملف بيانات قضية غير صالح (يُتوقّع case_data.js).');}};r.readAsText(f);};

  /* ===== قفل بكلمة مرور (تشفير محلي AES-GCM) ===== */
  document.getElementById('lockBtn').onclick=async function(){
    if(!window.APP_SHELL){alert('ميزة القفل تعمل من الملف الكامل فقط.');return;}
    var pw=window.prompt('اختر كلمة مرور لتشفير نسخة مقفلة من الملف:');if(!pw)return;
    try{
      var enc=new TextEncoder(),salt=crypto.getRandomValues(new Uint8Array(16)),iv=crypto.getRandomValues(new Uint8Array(12));
      var km=await crypto.subtle.importKey('raw',enc.encode(pw),{name:'PBKDF2'},false,['deriveKey']);
      var key=await crypto.subtle.deriveKey({name:'PBKDF2',salt:salt,iterations:150000,hash:'SHA-256'},km,{name:'AES-GCM',length:256},false,['encrypt']);
      var ct=await crypto.subtle.encrypt({name:'AES-GCM',iv:iv},key,enc.encode(JSON.stringify(window.CASE)));
      function b64(u){var s='';u=new Uint8Array(u);for(var i=0;i<u.length;i++)s+=String.fromCharCode(u[i]);return btoa(s);}
      var blob={salt:b64(salt),iv:b64(iv),ct:b64(ct)};
      var boot='<script>(function(){var B='+JSON.stringify(blob)+';function d(s){return Uint8Array.from(atob(s),function(c){return c.charCodeAt(0);});}'+
        'async function go(){var pw=prompt("أدخل كلمة المرور:");if(pw==null)return;try{var e=new TextEncoder();'+
        'var km=await crypto.subtle.importKey("raw",e.encode(pw),{name:"PBKDF2"},false,["deriveKey"]);'+
        'var k=await crypto.subtle.deriveKey({name:"PBKDF2",salt:d(B.salt),iterations:150000,hash:"SHA-256"},km,{name:"AES-GCM",length:256},false,["decrypt"]);'+
        'var pt=await crypto.subtle.decrypt({name:"AES-GCM",iv:d(B.iv)},k,d(B.ct));'+
        'window.CASE=JSON.parse(new TextDecoder().decode(pt));window.startApp();}catch(x){alert("كلمة مرور خاطئة.");go();}}go();})();<\/script>';
      var html=window.APP_SHELL.replace('__BOOTSTRAP__',boot);
      dl('واجهة_القضية_مقفلة.html',html,'text/html;charset=utf-8');
      alert('تم إنشاء نسخة مقفلة. ستطلب كلمة المرور عند فتحها.');
    }catch(e){alert('تعذّر التشفير في هذا المتصفّح.');}
  };
};
if(window.CASE&&window.startApp){window.startApp();}
</script>
</body>
</html>
"""

if __name__ == "__main__":
    main()
