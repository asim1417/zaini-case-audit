#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
tool_app.py — أداة عامة قابلة للنشر: يرفع المستخدم وثائقه فتُستخرَج وتُنظَّف وتُفهرَس وتُعرَض للبحث.
لا تحتوي أي بيانات قضية — آمنة للتداول. تعمل على أي خادم Python (مثل خادمك «حكيم»).

الميزات: رفع ملفات (نص/‏Word/‏PDF/صور) → استخراج نص → تطبيع وتنظيف عربي → فهرسة بحث (FTS) → عرض.
الأمان (اختياري): APP_PASSWORD يقفل الأداة خلف تسجيل دخول.

التشغيل:  APP_PASSWORD=اختياري  uvicorn tool_app:app --host 0.0.0.0 --port 8080
المتطلبات الأساسية: fastapi, uvicorn, python-multipart, python-docx.
اختياري لـPDF/الصور: pdfminer.six (نص PDF) · pytesseract + pdf2image + Pillow (OCR للمسح).
"""
import os, re, io, json, hmac, hashlib, sqlite3, tempfile
from fastapi import FastAPI, Request, UploadFile, File, Form, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

APP_PASSWORD = os.environ.get("APP_PASSWORD", "")
SECRET = os.environ.get("SESSION_SECRET", "") or (APP_PASSWORD + "::tool::salt")
DB = os.environ.get("TOOL_DB", os.path.join(tempfile.gettempdir(), "tool_docs.db"))
COOKIE = "tool_auth"
app = FastAPI(title="أداة معالجة الوثائق العربية", docs_url=None, redoc_url=None)

# ---------- تنظيف/تطبيع عربي ----------
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


def norm(s):
    out = []
    for ch in s or "":
        c = ord(ch)
        if 0x064B <= c <= 0x0652 or c in (0x0640, 0x0670):
            continue
        out.append({"أ": "ا", "إ": "ا", "آ": "ا", "ٱ": "ا", "ة": "ه", "ى": "ي",
                    "ؤ": "و", "ئ": "ي"}.get(ch, ch.lower()))
    return "".join(out)


# ---------- استخراج النص من الملفات ----------
def extract_text(name, data):
    ext = os.path.splitext(name)[1].lower()
    try:
        if ext in (".txt", ".md", ".csv", ".json"):
            return data.decode("utf-8", "ignore"), "نص"
        if ext == ".docx":
            from docx import Document
            d = Document(io.BytesIO(data))
            return "\n".join(p.text for p in d.paragraphs), "Word"
        if ext == ".pdf":
            try:
                from pdfminer.high_level import extract_text as pdftext
                txt = pdftext(io.BytesIO(data)) or ""
                if len(re.findall(r"[؀-ۿ]", txt)) > 30:
                    return txt, "PDF (نص)"
            except Exception:
                pass
            return _ocr_pdf(data)
        if ext in (".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp"):
            return _ocr_image(data)
    except Exception as e:
        return "", "تعذّر (%s)" % str(e)[:40]
    return "", "صيغة غير مدعومة"


def _ocr_image(data):
    try:
        import pytesseract
        from PIL import Image
        return pytesseract.image_to_string(Image.open(io.BytesIO(data)).convert("RGB"), lang="ara"), "صورة (OCR)"
    except Exception:
        return "", "صورة — تحتاج OCR (ثبّت pytesseract+tesseract-ara)"


def _ocr_pdf(data):
    try:
        import pytesseract
        from pdf2image import convert_from_bytes
        pages = convert_from_bytes(data, dpi=200)
        return "\n".join(pytesseract.image_to_string(p, lang="ara") for p in pages), "PDF ممسوح (OCR)"
    except Exception:
        return "", "PDF ممسوح — تحتاج OCR (pytesseract+pdf2image+poppler)"


# ---------- قاعدة البيانات ----------
def _db():
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    con.executescript("""
      CREATE TABLE IF NOT EXISTS docs(id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT, kind TEXT,
        full_text TEXT, norm_text TEXT);
      CREATE VIRTUAL TABLE IF NOT EXISTS fts USING fts5(body);
    """)
    return con


# ---------- المصادقة ----------
def _token():
    return hmac.new(SECRET.encode(), b"ok", hashlib.sha256).hexdigest()


def _authed(req):
    return (not APP_PASSWORD) or req.cookies.get(COOKIE) == _token()


LOGIN = """<!doctype html><html lang=ar dir=rtl><meta charset=utf-8><meta name=viewport content="width=device-width,initial-scale=1">
<title>دخول</title><style>body{font-family:Tahoma;background:#0f172a;color:#e5e7eb;display:flex;min-height:100vh;align-items:center;justify-content:center;margin:0}
.b{background:#1e293b;padding:26px;border-radius:14px;width:300px}input{width:100%;padding:11px;margin:9px 0;border-radius:9px;border:1px solid #334155;background:#0f172a;color:#fff;box-sizing:border-box}
button{width:100%;padding:11px;border:0;border-radius:9px;background:#2563eb;color:#fff;font-size:16px}</style>
<div class=b><h2>أداة معالجة الوثائق</h2><form method=post action=/login><input type=password name=password placeholder="كلمة المرور" autofocus>
<div style="color:#fca5a5;font-size:13px">__E__</div><button>دخول</button></form></div></html>"""


@app.post("/login")
def login(password: str = Form("")):
    if APP_PASSWORD and hmac.compare_digest(password, APP_PASSWORD):
        r = RedirectResponse("/", status_code=303)
        r.set_cookie(COOKIE, _token(), httponly=True, samesite="lax", max_age=604800)
        return r
    return HTMLResponse(LOGIN.replace("__E__", "كلمة مرور خاطئة"), 401)


def _guard(req):
    if not _authed(req):
        raise HTTPException(401, "غير مصرّح")


# ---------- API ----------
@app.post("/api/upload")
async def upload(req: Request, files: list[UploadFile] = File(...)):
    _guard(req)
    con = _db(); added = []
    for f in files:
        data = await f.read()
        txt, kind = extract_text(f.filename, data)
        txt = clean_text(txt or "")
        cur = con.execute("INSERT INTO docs(title,kind,full_text,norm_text) VALUES(?,?,?,?)",
                          (f.filename, kind, txt, norm(txt)))
        con.execute("INSERT INTO fts(rowid,body) VALUES(?,?)", (cur.lastrowid, norm(txt)))
        added.append({"id": cur.lastrowid, "title": f.filename, "kind": kind,
                      "chars": len(txt), "ok": bool(txt.strip())})
    con.commit(); con.close()
    return JSONResponse({"added": added})


@app.get("/api/docs")
def api_docs(req: Request):
    _guard(req)
    con = _db(); rows = con.execute("SELECT id,title,kind,length(full_text) AS n FROM docs ORDER BY id DESC").fetchall(); con.close()
    return JSONResponse([dict(r) for r in rows])


@app.get("/api/search")
def api_search(req: Request, q: str = ""):
    _guard(req)
    q = (q or "").strip()
    if not q:
        return JSONResponse([])
    toks = [t for t in re.split(r"\s+", norm(q)) if len(t) >= 2]
    con = _db()
    try:
        match = " ".join('"%s"*' % t for t in toks)
        rows = con.execute("SELECT d.id,d.title,d.kind,snippet(fts,0,'«','»','…',12) AS snip "
                           "FROM fts JOIN docs d ON d.id=fts.rowid WHERE fts MATCH ? ORDER BY rank LIMIT 300",
                           (match,)).fetchall()
    except Exception:
        rows = con.execute("SELECT id,title,kind,'' AS snip FROM docs WHERE norm_text LIKE ? LIMIT 300",
                           ("%" + norm(q) + "%",)).fetchall()
    con.close()
    return JSONResponse([dict(r) for r in rows])


@app.get("/api/doc/{i}")
def api_doc(req: Request, i: int):
    _guard(req)
    con = _db(); r = con.execute("SELECT id,title,kind,full_text FROM docs WHERE id=?", (i,)).fetchone(); con.close()
    if not r:
        raise HTTPException(404)
    return JSONResponse(dict(r))


@app.post("/api/clear")
def api_clear(req: Request):
    _guard(req)
    con = _db(); con.executescript("DELETE FROM docs; DELETE FROM fts;"); con.commit(); con.close()
    return JSONResponse({"ok": True})


@app.get("/healthz")
def health():
    return {"ok": True}


# ---------- الواجهة ----------
PAGE = r"""<!doctype html><html lang=ar dir=rtl><meta charset=utf-8><meta name=viewport content="width=device-width,initial-scale=1">
<title>أداة معالجة الوثائق العربية</title>
<style>
:root{--bg:#f6f7f9;--pane:#fff;--ink:#1f2937;--mut:#6b7280;--line:#e5e7eb;--accent:#2563eb}
*{box-sizing:border-box}body{margin:0;font-family:Tahoma,Arial;background:var(--bg);color:var(--ink)}
header{background:var(--pane);border-bottom:1px solid var(--line);padding:9px 12px;display:flex;gap:8px;align-items:center;position:sticky;top:0;flex-wrap:wrap}
header b{font-size:15px}#q{flex:1;min-width:160px;padding:9px 11px;border:1px solid var(--line);border-radius:9px;font-size:16px}
.btn{padding:8px 12px;border:1px solid var(--accent);background:var(--accent);color:#fff;border-radius:9px;cursor:pointer;font-size:14px}
.btn.alt{background:#fff;color:var(--accent)}
.wrap{display:flex;height:calc(100vh - 56px)}
.side{width:340px;max-width:44vw;border-inline-start:1px solid var(--line);overflow:auto;background:var(--pane)}
.it{padding:9px 12px;border-bottom:1px solid var(--line);cursor:pointer}.it:hover{background:#eff6ff}
.it .t{font-size:14px}.it .s{color:var(--mut);font-size:12px}
main{flex:1;overflow:auto;padding:16px}
.drop{border:2px dashed var(--line);border-radius:12px;padding:26px;text-align:center;color:var(--mut);margin-bottom:14px}
.drop.hl{border-color:var(--accent);background:#eff6ff}
.txt{white-space:pre-wrap;line-height:1.95;font-size:18px;font-family:"Traditional Arabic","Simplified Arabic",Tahoma,serif;direction:rtl}
mark{background:#fde68a}.cnt{color:var(--mut);font-size:12px;padding:6px 12px}.kind{color:var(--accent);font-size:11px}
@media(max-width:760px){.wrap{flex-direction:column;height:auto}.side{width:auto;max-width:none;max-height:42vh}}
</style>
<header><b>أداة معالجة الوثائق العربية</b>
  <input id=q placeholder="بحث في وثائقك…">
  <label class="btn">➕ إرفاق ملفات<input id=file type=file multiple style=display:none accept=".txt,.md,.csv,.json,.docx,.pdf,.png,.jpg,.jpeg,.tif,.tiff"></label>
  <button class="btn alt" id=clr>🗑️ مسح الكل</button>
  <span id=cnt class=cnt></span>__LOGOUT__
</header>
<div class=wrap>
  <aside class=side id=list></aside>
  <main id=detail>
    <div class=drop id=drop>📎 اسحب ملفاتك هنا أو اضغط «إرفاق ملفات».<br><small>نص/‏Word/‏PDF/صور — تُستخرَج وتُفهرَس محلياً على خادمك.</small></div>
    <div id=view style="color:#6b7280;text-align:center;margin-top:20px">ارفع وثائق ثم ابحث فيها.</div>
  </main>
</div>
<script>
var listEl=document.getElementById('list'),view=document.getElementById('view'),q=document.getElementById('q'),cnt=document.getElementById('cnt'),drop=document.getElementById('drop');
var curTokens=[];
function esc(s){return (s||'').replace(/[&<>]/g,function(c){return{'&':'&amp;','<':'&lt;','>':'&gt;'}[c];});}
function nrm(s){var o='';for(var i=0;i<s.length;i++){var ch=s[i],c=ch.charCodeAt(0);
 if(c>=0x064B&&c<=0x0652||c===0x0640||c===0x0670)continue;o+=({'أ':'ا','إ':'ا','آ':'ا','ٱ':'ا','ة':'ه','ى':'ي','ؤ':'و','ئ':'ي'}[ch]||ch.toLowerCase());}return o;}
function api(m,u,b,cb){var x=new XMLHttpRequest();x.open(m,u);x.onload=function(){if(x.status==200)cb(x.responseText?JSON.parse(x.responseText):null);else if(x.status==401)location='/login';};if(b)x.send(b);else x.send();}
function row(d){return '<div class=it data-id="'+d.id+'"><div class=t>'+esc(d.title)+' <span class=kind>['+esc(d.kind||'')+']</span></div>'+(d.snip?'<div class=s>'+esc(d.snip).replace(/«/g,'<mark>').replace(/»/g,'</mark>')+'</div>':'')+'</div>';}
function bind(){[].forEach.call(listEl.querySelectorAll('.it'),function(el){el.onclick=function(){openDoc(el.getAttribute('data-id'));};});}
function showList(a){cnt.textContent=a.length+' وثيقة';listEl.innerHTML=a.map(row).join('')||'<div class=cnt>لا نتائج.</div>';bind();}
function refresh(){var v=q.value.trim();if(!v){curTokens=[];api('GET','/api/docs',null,showList);}else{curTokens=nrm(v).split(/\s+/).filter(function(t){return t.length>=2;});api('GET','/api/search?q='+encodeURIComponent(v),null,showList);}}
function hl(t){var e=esc(t);if(!curTokens.length)return e;var nb=nrm(t),marks=[];curTokens.forEach(function(tok){var i=0;while((i=nb.indexOf(tok,i))>=0){marks.push([i,i+tok.length]);i+=tok.length;}});
 if(!marks.length)return e;marks.sort(function(a,b){return a[0]-b[0];});var o='',p=0;marks.forEach(function(m){if(m[0]<p)return;o+=esc(t.slice(p,m[0]))+'<mark>'+esc(t.slice(m[0],m[1]))+'</mark>';p=m[1];});return o+esc(t.slice(p));}
function openDoc(id){api('GET','/api/doc/'+id,null,function(d){document.getElementById('detail').innerHTML='<h2>'+esc(d.title)+' <span class=kind>['+esc(d.kind||'')+']</span></h2><hr><div class=txt>'+hl(d.full_text||'(لا نص مستخرج)')+'</div>';});}
function upload(files){if(!files.length)return;var fd=new FormData();for(var i=0;i<files.length;i++)fd.append('files',files[i]);
 cnt.textContent='جارٍ الرفع والمعالجة…';api('POST','/api/upload',fd,function(r){var ok=r.added.filter(function(x){return x.ok;}).length;cnt.textContent='أُضيف '+r.added.length+' (نجح استخراج '+ok+')';refresh();});}
document.getElementById('file').onchange=function(e){upload(e.target.files);};
['dragenter','dragover'].forEach(function(ev){drop.addEventListener(ev,function(e){e.preventDefault();drop.classList.add('hl');});});
['dragleave','drop'].forEach(function(ev){drop.addEventListener(ev,function(e){e.preventDefault();drop.classList.remove('hl');});});
drop.addEventListener('drop',function(e){upload(e.dataTransfer.files);});
document.getElementById('clr').onclick=function(){if(confirm('مسح كل الوثائق المرفوعة؟'))api('POST','/api/clear',new FormData(),function(){refresh();document.getElementById('detail').innerHTML='<div class=drop id=drop2>📎 ارفع وثائق جديدة.</div>';});};
var t;q.oninput=function(){clearTimeout(t);t=setTimeout(refresh,200);};
refresh();
</script></html>"""


@app.get("/", response_class=HTMLResponse)
def home(req: Request):
    if not _authed(req):
        return HTMLResponse(LOGIN.replace("__E__", ""))
    logout = ('<a href="/logout" style="font-size:12px;margin-inline-start:auto">خروج</a>' if APP_PASSWORD else '')
    return HTMLResponse(PAGE.replace("__LOGOUT__", logout))


@app.get("/logout")
def logout():
    r = RedirectResponse("/"); r.delete_cookie(COOKIE); return r
