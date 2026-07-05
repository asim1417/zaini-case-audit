#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
case_server.py — خادم ويب للقضية: قاعدة بيانات على الخادم + واجهة خفيفة محميّة بكلمة مرور.

البيانات تبقى على الخادم؛ الواجهة تجلب نتيجة بحث أو وثيقة واحدة فقط (خفيفة على الجوال).
الحماية: لا يُعرض شيء قبل تسجيل الدخول بكلمة المرور (APP_PASSWORD).

التشغيل المحلي:
  CASE_DB=case.db APP_PASSWORD=اختر_كلمة uvicorn case_server:app --host 0.0.0.0 --port 8080
"""
import os, re, json, hmac, hashlib, sqlite3, html
from fastapi import FastAPI, Request, Form, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

CASE_DB = os.environ.get("CASE_DB", "case.db")
APP_PASSWORD = os.environ.get("APP_PASSWORD", "")
SECRET = os.environ.get("SESSION_SECRET", "") or (APP_PASSWORD + "::case::salt")
COOKIE = "case_auth"

app = FastAPI(title="قاعدة بيانات القضية", docs_url=None, redoc_url=None)


def _token():
    return hmac.new(SECRET.encode(), b"authorized", hashlib.sha256).hexdigest()


def _authed(req: Request):
    return APP_PASSWORD and req.cookies.get(COOKIE) == _token()


def _db():
    con = sqlite3.connect(CASE_DB)
    con.row_factory = sqlite3.Row
    return con


def _norm(s):
    out = []
    for ch in s or "":
        c = ord(ch)
        if 0x064B <= c <= 0x0652 or c in (0x0640, 0x0670):
            continue
        out.append({"أ": "ا", "إ": "ا", "آ": "ا", "ٱ": "ا", "ة": "ه", "ى": "ي",
                    "ؤ": "و", "ئ": "ي"}.get(ch, ch.lower()))
    return "".join(out)


# ---------- صفحات ----------
LOGIN = """<!doctype html><html lang=ar dir=rtl><meta charset=utf-8>
<meta name=viewport content="width=device-width,initial-scale=1"><title>دخول — قاعدة بيانات القضية</title>
<style>body{font-family:Tahoma,Arial;background:#0f172a;color:#e5e7eb;display:flex;min-height:100vh;align-items:center;justify-content:center;margin:0}
.box{background:#1e293b;padding:28px;border-radius:14px;width:300px;max-width:90vw}
input{width:100%;padding:11px;border-radius:9px;border:1px solid #334155;background:#0f172a;color:#fff;font-size:16px;margin:10px 0;box-sizing:border-box}
button{width:100%;padding:11px;border:0;border-radius:9px;background:#2563eb;color:#fff;font-size:16px;cursor:pointer}
h2{margin:0 0 6px}.e{color:#fca5a5;font-size:13px;min-height:18px}</style>
<div class=box><h2>قاعدة بيانات القضية</h2><div style="color:#94a3b8;font-size:13px">محمية — أدخل كلمة المرور</div>
<form method=post action=/login><input type=password name=password placeholder="كلمة المرور" autofocus>
<div class=e>__ERR__</div><button>دخول</button></form></div></html>"""


@app.get("/", response_class=HTMLResponse)
def root(req: Request):
    if not APP_PASSWORD:
        return HTMLResponse("<h3 dir=rtl>اضبط APP_PASSWORD في إعدادات الاستضافة أولاً.</h3>", 500)
    if _authed(req):
        return RedirectResponse("/app")
    return HTMLResponse(LOGIN.replace("__ERR__", ""))


@app.post("/login")
def login(password: str = Form("")):
    if APP_PASSWORD and hmac.compare_digest(password, APP_PASSWORD):
        r = RedirectResponse("/app", status_code=303)
        r.set_cookie(COOKIE, _token(), httponly=True, samesite="lax", max_age=86400 * 7)
        return r
    return HTMLResponse(LOGIN.replace("__ERR__", "كلمة مرور خاطئة"), 401)


@app.get("/logout")
def logout():
    r = RedirectResponse("/")
    r.delete_cookie(COOKIE)
    return r


# ---------- API ----------
def _guard(req):
    if not _authed(req):
        raise HTTPException(401, "غير مصرّح")


@app.get("/api/list")
def api_list(req: Request):
    _guard(req)
    con = _db()
    rows = con.execute("SELECT id,n,title,doc_type,date,quality,distorted FROM docs ORDER BY n").fetchall()
    con.close()
    return JSONResponse([dict(r) for r in rows])


@app.get("/api/search")
def api_search(req: Request, q: str = ""):
    _guard(req)
    q = (q or "").strip()
    if not q:
        return JSONResponse([])
    toks = [t for t in re.split(r"\s+", _norm(q)) if len(t) >= 2]
    if not toks:
        return JSONResponse([])
    match = " ".join('"%s"*' % t.replace('"', '') for t in toks)
    con = _db()
    try:
        rows = con.execute(
            "SELECT d.id,d.title,d.doc_type,d.date,d.distorted,"
            "snippet(fts,2,'«','»','…',14) AS snip "
            "FROM fts JOIN docs d ON d.id=fts.id WHERE fts MATCH ? ORDER BY rank LIMIT 400",
            (match,)).fetchall()
    except Exception:
        like = "%" + _norm(q) + "%"
        rows = con.execute("SELECT id,title,doc_type,date,distorted,'' AS snip FROM docs "
                           "WHERE norm_text LIKE ? LIMIT 400", (like,)).fetchall()
    con.close()
    return JSONResponse([dict(r) for r in rows])


@app.get("/api/doc/{doc_id}")
def api_doc(req: Request, doc_id: str):
    _guard(req)
    con = _db()
    r = con.execute("SELECT id,title,doc_type,date,quality,distorted,dist_reason,view_url,card,entities,full_text "
                    "FROM docs WHERE id=?", (doc_id,)).fetchone()
    con.close()
    if not r:
        raise HTTPException(404, "غير موجود")
    d = dict(r)
    d["card"] = json.loads(d.get("card") or "{}")
    d["entities"] = json.loads(d.get("entities") or "{}")
    return JSONResponse(d)


# ---------- الواجهة (خفيفة، تجلب من API) ----------
APP_HTML = r"""<!doctype html><html lang=ar dir=rtl><meta charset=utf-8>
<meta name=viewport content="width=device-width,initial-scale=1"><title>قاعدة بيانات القضية</title>
<style>
:root{--bg:#f6f7f9;--pane:#fff;--ink:#1f2937;--mut:#6b7280;--line:#e5e7eb;--accent:#2563eb}
*{box-sizing:border-box}body{margin:0;font-family:Tahoma,Arial;background:var(--bg);color:var(--ink)}
header{background:var(--pane);border-bottom:1px solid var(--line);padding:8px 12px;display:flex;gap:8px;align-items:center;position:sticky;top:0}
header b{font-size:15px}#q{flex:1;padding:9px 11px;border:1px solid var(--line);border-radius:9px;font-size:16px}
.wrap{display:flex;height:calc(100vh - 54px)}
.side{width:340px;max-width:42vw;border-inline-start:1px solid var(--line);overflow:auto;background:var(--pane)}
.it{padding:9px 12px;border-bottom:1px solid var(--line);cursor:pointer}.it:hover{background:#eff6ff}
.it .t{font-size:14px}.it .s{color:var(--mut);font-size:12px}.dist{color:#b91c1c;font-size:11px}
main{flex:1;overflow:auto;padding:14px}
.txt{white-space:pre-wrap;line-height:1.95;font-size:18px;font-family:"Traditional Arabic","Simplified Arabic",Tahoma,serif;direction:rtl}
mark{background:#fde68a}.kv{color:var(--mut);font-size:13px;margin:4px 0}
a.src{color:var(--accent)} .cnt{color:var(--mut);font-size:12px;padding:6px 12px}
@media(max-width:760px){.wrap{flex-direction:column;height:auto}.side{width:auto;max-width:none;max-height:45vh}}
</style>
<header><b>القضية</b><input id=q placeholder="بحث…"><span id=cnt class=cnt></span><a href=/logout style="font-size:12px">خروج</a></header>
<div class=wrap><aside class=side id=list></aside><main id=detail><div style="color:#6b7280;margin-top:40px;text-align:center">اختر وثيقة أو ابحث.</div></main></div>
<script>
var listEl=document.getElementById('list'),det=document.getElementById('detail'),q=document.getElementById('q'),cnt=document.getElementById('cnt');
var curTokens=[];
function esc(s){return (s||'').replace(/[&<>]/g,function(c){return{'&':'&amp;','<':'&lt;','>':'&gt;'}[c];});}
function norm(s){var o='';for(var i=0;i<s.length;i++){var ch=s[i],c=ch.charCodeAt(0);
 if(c>=0x064B&&c<=0x0652||c===0x0640||c===0x0670)continue;
 o+=({'أ':'ا','إ':'ا','آ':'ا','ٱ':'ا','ة':'ه','ى':'ي','ؤ':'و','ئ':'ي'}[ch]||ch.toLowerCase());}return o;}
function row(d){var s=esc(d.title)+(d.distorted?' <span class=dist>⚠</span>':'');
 var snip=d.snip?'<div class=s>'+esc(d.snip).replace(/«/g,'<mark>').replace(/»/g,'</mark>')+'</div>':'';
 return '<div class=it data-id="'+esc(d.id)+'"><div class=t>'+s+'</div><div class=s>'+esc(d.doc_type||'')+(d.date?' · '+esc(d.date):'')+'</div>'+snip+'</div>';}
function bind(){Array.prototype.forEach.call(listEl.querySelectorAll('.it'),function(el){el.onclick=function(){openDoc(el.getAttribute('data-id'));};});}
function load(url,cb){var x=new XMLHttpRequest();x.open('GET',url);x.onload=function(){if(x.status==200)cb(JSON.parse(x.responseText));else if(x.status==401)location='/';};x.send();}
function showList(arr){cnt.textContent=arr.length+' نتيجة';listEl.innerHTML=arr.map(row).join('')||'<div class=cnt>لا نتائج.</div>';bind();}
function refresh(){var v=q.value.trim();if(!v){load('/api/list',showList);curTokens=[];}else{curTokens=norm(v).split(/\s+/).filter(function(t){return t.length>=2;});load('/api/search?q='+encodeURIComponent(v),showList);}}
function hl(text){var t=esc(text);if(!curTokens.length)return t;
 var nb=norm(text);var marks=[];curTokens.forEach(function(tok){var i=0;while((i=nb.indexOf(tok,i))>=0){marks.push([i,i+tok.length]);i+=tok.length;}});
 if(!marks.length)return t; // علّم على النص المُطبَّع تقريبياً
 marks.sort(function(a,b){return a[0]-b[0];});var out='',p=0;
 marks.forEach(function(m){if(m[0]<p)return;out+=esc(text.slice(p,m[0]))+'<mark>'+esc(text.slice(m[0],m[1]))+'</mark>';p=m[1];});out+=esc(text.slice(p));return out;}
function openDoc(id){load('/api/doc/'+encodeURIComponent(id),function(d){
 var e=d.entities||{},parts=(e.parties||[]).concat(e.company||[]).join('، ');
 det.innerHTML='<h2>'+esc(d.title)+'</h2>'+
  '<div class=kv>'+esc(d.doc_type||'')+(d.date?' · '+esc(d.date):'')+(d.distorted?' · <span class=dist>⚠ '+esc(d.dist_reason||'مشوّه')+'</span>':'')+'</div>'+
  (parts?'<div class=kv>الأطراف: '+esc(parts)+'</div>':'')+
  (d.view_url?'<div class=kv><a class=src target=_blank href="'+esc(d.view_url)+'">فتح الأصل ↗</a></div>':'')+
  '<hr><div class=txt>'+hl(d.full_text||'(لا نص)')+'</div>';
 det.scrollTop=0;
});}
var t;q.oninput=function(){clearTimeout(t);t=setTimeout(refresh,200);};
refresh();
</script></html>"""


@app.get("/app", response_class=HTMLResponse)
def app_page(req: Request):
    if not _authed(req):
        return RedirectResponse("/")
    return HTMLResponse(APP_HTML)


@app.get("/healthz")
def healthz():
    return {"ok": True, "db": os.path.exists(CASE_DB)}
