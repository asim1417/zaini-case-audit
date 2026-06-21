#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
make_viewer.py — توليد واجهة تصفّح أمامية (HTML) لمخرجات الفحص.

ينتج مجلد viewer/ فيه:
  - case_data.js : بيانات القضية (مستندات + جداول) مضمّنة كـ window.CASE
  - index.html   : واجهة عربية للبحث والتصفّح والتصدير وعرض النص الكامل

يعمل محلياً (ملف file://) وعلى GitHub Pages بنفس الملفات (يُحمّل case_data.js
عبر وسم <script> فيتجاوز قيود fetch المحلية).

المصدر: outputs/json/full_documents.jsonl + بعض جداول outputs/csv (إن وُجدت).
كل المخرجات «مساعدة آلية تحتاج مراجعة بشرية».
"""
import os, json, csv, io, datetime
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
OUTPUT_ROOT = Path(os.environ.get("CASE_ROOT") or SCRIPT_DIR.parent)
OUT = OUTPUT_ROOT / "outputs"
VIEWER = OUTPUT_ROOT / "viewer"
DOCS_JSONL = OUT / "json" / "full_documents.jsonl"
CSV_DIR = OUT / "csv"


def load_docs():
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
        docs.append({
            "id": r.get("id", ""),
            "title": r.get("title", ""),
            "doc_type": r.get("doc_type", "غير مصنف"),
            "parent_path": r.get("parent_path", ""),
            "viewUrl": r.get("viewUrl", ""),
            "card": r.get("card", {}) or {},
            "entities": r.get("entities", {}) or {},
            "full_text": r.get("full_text", "") or "",
        })
    return docs


def load_csv(name):
    p = CSV_DIR / name
    if not p.exists():
        return None
    txt = p.read_text(encoding="utf-8-sig", errors="replace")
    rows = list(csv.reader(io.StringIO(txt)))
    if not rows:
        return None
    return {"header": rows[0], "rows": rows[1:]}


def main():
    docs = load_docs()
    tables = {}
    for key, fname in {
        "timeline": "08_timeline_gregorian.csv",
        "deeds": "12_deeds_register.csv",
        "amounts": "09_central_amounts.csv",
        "grounds": "10_objection_cassation_grounds.csv",
        "laws": "11_central_law_references.csv",
        "milestones": "13_key_milestones.csv",
    }.items():
        t = load_csv(fname)
        if t:
            tables[key] = t

    case_no = ""
    cfg = OUTPUT_ROOT / "case_config.json"
    if cfg.exists():
        try:
            c = json.loads(cfg.read_text(encoding="utf-8"))
            case_no = c.get("case", {}).get("number", "")
        except Exception:
            pass

    data = {
        "generated": datetime.datetime.now().strftime("%Y-%m-%d %H:%M"),
        "case_number": case_no,
        "doc_count": len(docs),
        "docs": docs,
        "tables": tables,
    }

    VIEWER.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(data, ensure_ascii=False)
    (VIEWER / "case_data.js").write_text("window.CASE = " + payload + ";\n", encoding="utf-8")
    (VIEWER / "index.html").write_text(INDEX_HTML, encoding="utf-8")
    print("viewer ready:", VIEWER)
    print("docs:", len(docs), "| tables:", list(tables.keys()))


INDEX_HTML = r"""<!DOCTYPE html>
<html lang="ar" dir="rtl">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>واجهة تصفّح القضية — مخرج آلي يحتاج مراجعة بشرية</title>
<style>
  :root{--bg:#f6f7f9;--pane:#fff;--ink:#1f2937;--mut:#6b7280;--line:#e5e7eb;
        --accent:#2563eb;--accent2:#eff6ff;--warn:#fde68a;--chip:#f1f5f9;
        --tsize:14.5px;--tlh:1.85;--tfam:inherit;--talign:start;}
  *{box-sizing:border-box}
  body{margin:0;font-family:"Segoe UI",Tahoma,Arial,sans-serif;background:var(--bg);
       color:var(--ink);font-size:15px;line-height:1.7}
  header{background:var(--pane);border-bottom:1px solid var(--line);padding:8px 16px;
         display:flex;gap:10px;align-items:center;flex-wrap:wrap;position:sticky;top:0;z-index:6}
  header h1{font-size:17px;margin:0}
  .banner{background:var(--warn);color:#7c2d12;font-size:12.5px;padding:4px 10px;border-radius:6px}
  .meta{color:var(--mut);font-size:12.5px;margin-inline-start:auto}
  .fontbar{display:flex;gap:6px;align-items:center;flex-wrap:wrap;font-size:12.5px;color:var(--mut)}
  .fontbar .grp{display:flex;gap:2px;align-items:center;background:var(--bg);border:1px solid var(--line);
       border-radius:8px;padding:2px 6px}
  .fontbar button{border:none;background:transparent;cursor:pointer;font-size:14px;padding:1px 6px;border-radius:6px}
  .fontbar button:hover{background:var(--accent2)}
  .fontbar select{border:none;background:transparent;font-family:inherit;font-size:12.5px;cursor:pointer}
  .tabs{display:flex;gap:6px;flex-wrap:wrap;padding:10px 16px 0}
  .tab{padding:6px 14px;border:1px solid var(--line);background:var(--pane);border-radius:20px;
       cursor:pointer;font-size:13px}
  .tab.active{background:var(--accent);color:#fff;border-color:var(--accent)}
  .wrap{display:flex;height:calc(100vh - 100px)}
  .side{width:370px;min-width:280px;background:var(--pane);border-inline-start:1px solid var(--line);
        display:flex;flex-direction:column}
  .controls{padding:10px;border-bottom:1px solid var(--line)}
  .controls input,.controls select{width:100%;padding:8px 10px;border:1px solid var(--line);
        border-radius:8px;font-size:14px;margin-bottom:6px;font-family:inherit}
  .selrow{display:flex;gap:6px;align-items:center;flex-wrap:wrap;font-size:12.5px}
  .selrow button{padding:4px 9px;border:1px solid var(--line);background:var(--pane);border-radius:7px;cursor:pointer;font-size:12.5px}
  .selrow button:hover{background:var(--accent2)}
  .btn-export{background:var(--accent)!important;color:#fff;border-color:var(--accent)!important;font-weight:600}
  .selcount{color:var(--accent);font-weight:600}
  .count{font-size:12px;color:var(--mut);padding:2px 4px}
  .list{overflow:auto;flex:1}
  .item{padding:8px 10px;border-bottom:1px solid var(--line);cursor:pointer;display:flex;gap:8px;align-items:flex-start}
  .item:hover{background:var(--accent2)}
  .item.active{background:var(--accent2);border-inline-start:3px solid var(--accent)}
  .item input{margin-top:3px;flex:none;width:16px;height:16px;cursor:pointer}
  .item .t{font-size:13.5px;font-weight:600;word-break:break-word}
  .item .s{font-size:11.5px;color:var(--mut);margin-top:2px}
  main{flex:1;overflow:auto;padding:18px 22px}
  .card{background:var(--pane);border:1px solid var(--line);border-radius:12px;padding:14px 16px;margin-bottom:14px}
  .card h2{margin:0 0 8px;font-size:16px}
  .kv{display:grid;grid-template-columns:140px 1fr;gap:4px 12px;font-size:13.5px}
  .kv b{color:var(--mut);font-weight:600}
  .chips span{display:inline-block;background:var(--accent2);color:#1e40af;border-radius:16px;
       padding:2px 10px;font-size:12px;margin:2px}
  .txt{white-space:pre-wrap;word-break:break-word;background:var(--pane);border:1px solid var(--line);
       border-radius:12px;padding:14px 16px;
       font-size:var(--tsize);line-height:var(--tlh);font-family:var(--tfam);text-align:var(--talign)}
  mark{background:#fde68a}
  .empty{color:var(--mut);text-align:center;margin-top:60px}
  table{border-collapse:collapse;width:100%;font-size:13px;background:var(--pane)}
  th,td{border:1px solid var(--line);padding:6px 9px;text-align:start;vertical-align:top}
  th{background:var(--accent2);position:sticky;top:0}
  a{color:var(--accent)}
  .openlink{font-size:12.5px}
  /* لوحة التصدير */
  .modal{position:fixed;inset:0;background:rgba(0,0,0,.35);z-index:20;display:none;align-items:center;justify-content:center}
  .modal.open{display:flex}
  .panel{background:var(--pane);border-radius:14px;padding:18px 20px;width:min(440px,92vw);box-shadow:0 10px 40px rgba(0,0,0,.2)}
  .panel h3{margin:0 0 12px}
  .panel .opt{margin:8px 0;font-size:14px}
  .panel label{cursor:pointer}
  .panel .acts{display:flex;gap:8px;flex-wrap:wrap;margin-top:14px}
  .panel .acts button{flex:1;min-width:120px;padding:9px;border-radius:9px;border:1px solid var(--accent);
       background:var(--accent);color:#fff;cursor:pointer;font-size:13.5px;font-family:inherit}
  .panel .acts button.alt{background:var(--pane);color:var(--accent)}
  .panel .x{float:left;cursor:pointer;color:var(--mut);font-size:18px;border:none;background:none}
  @media(max-width:760px){.wrap{flex-direction:column;height:auto}.side{width:auto}main{height:auto}}
</style>
</head>
<body>
<header>
  <h1>واجهة تصفّح القضية</h1>
  <span class="banner">مخرج آلي يحتاج مراجعة بشرية</span>
  <div class="fontbar">
    <span class="grp">نص<button id="fMinus" title="تصغير">A−</button><button id="fPlus" title="تكبير">A+</button></span>
    <span class="grp">أسطر<button id="lMinus" title="تقليل">−</button><button id="lPlus" title="زيادة">+</button></span>
    <span class="grp">خط
      <select id="fFam">
        <option value="inherit">افتراضي</option>
        <option value="'Traditional Arabic','Amiri',serif">نسخ تقليدي</option>
        <option value="'Tahoma',Arial,sans-serif">واضح</option>
        <option value="'Courier New',monospace">بعرض ثابت</option>
      </select>
    </span>
    <span class="grp"><label><input type="checkbox" id="fJustify"> ضبط الأسطر</label></span>
  </div>
  <span class="meta" id="meta"></span>
</header>

<div class="tabs">
  <div class="tab active" data-view="docs">المستندات</div>
  <div class="tab" data-view="timeline">الخط الزمني</div>
  <div class="tab" data-view="deeds">الصكوك</div>
  <div class="tab" data-view="amounts">المبالغ</div>
  <div class="tab" data-view="grounds">أسباب النقض</div>
  <div class="tab" data-view="laws">الأنظمة</div>
  <div class="tab" data-view="milestones">المحطات</div>
</div>

<div id="docsView" class="wrap">
  <aside class="side">
    <div class="controls">
      <input id="q" placeholder="بحث في العناوين والنصوص…">
      <select id="type"><option value="">كل الأنواع</option></select>
      <div class="selrow">
        <button id="selAll">تحديد المطابق</button>
        <button id="selNone">إلغاء التحديد</button>
        <button id="exportBtn" class="btn-export">تصدير ▾</button>
        <span class="selcount" id="selCount">المحدد: 0</span>
      </div>
      <div class="count" id="count"></div>
    </div>
    <div class="list" id="list"></div>
  </aside>
  <main id="detail"><div class="empty">اختر مستنداً من القائمة لعرض بطاقته ونصّه الكامل.</div></main>
</div>

<div id="tableView" style="display:none;padding:0 16px 30px"></div>

<!-- لوحة التصدير -->
<div class="modal" id="exportModal">
  <div class="panel">
    <button class="x" id="exportClose">×</button>
    <h3>تصدير المستندات</h3>
    <div class="opt"><b>النطاق:</b><br>
      <label><input type="radio" name="scope" value="selected" checked> المحدد فقط (<span id="scSel">0</span>)</label><br>
      <label><input type="radio" name="scope" value="match"> المطابق للبحث الحالي (<span id="scMatch">0</span>)</label><br>
      <label><input type="radio" name="scope" value="all"> كل المستندات (<span id="scAll">0</span>)</label>
    </div>
    <div class="opt"><label><input type="checkbox" id="incText" checked> تضمين النص الكامل (إلغاؤه يصدّر البطاقات والروابط فقط)</label></div>
    <div class="acts">
      <button id="doWord">تنزيل Word</button>
      <button id="doPrint">طباعة / PDF</button>
      <button id="doHtml" class="alt">تنزيل HTML</button>
      <button id="doCsv" class="alt">بطاقات CSV</button>
    </div>
  </div>
</div>

<script src="case_data.js"></script>
<script>
(function(){
  var C = window.CASE || {docs:[],tables:{}};
  var docs = C.docs || [];
  document.getElementById('meta').textContent =
    'القضية ' + (C.case_number||'') + ' — ' + (C.doc_count||docs.length) + ' مستند — وُلِّد ' + (C.generated||'');

  var typeSel=document.getElementById('type');
  var types={}; docs.forEach(function(d){types[d.doc_type]=(types[d.doc_type]||0)+1;});
  Object.keys(types).sort().forEach(function(t){
    var o=document.createElement('option');o.value=t;o.textContent=t+' ('+types[t]+')';typeSel.appendChild(o);
  });

  var listEl=document.getElementById('list'),detailEl=document.getElementById('detail'),
      qEl=document.getElementById('q'),countEl=document.getElementById('count'),
      selCountEl=document.getElementById('selCount');
  var current=null,lastQ='',selected={};

  function esc(s){return (s||'').replace(/[&<>]/g,function(c){return{'&':'&amp;','<':'&lt;','>':'&gt;'}[c];});}
  function hi(s,q){s=esc(s);if(!q)return s;
    try{return s.replace(new RegExp('('+q.replace(/[.*+?^${}()|[\]\\]/g,'\\$&')+')','gi'),'<mark>$1</mark>');}catch(e){return s;}}
  function selectedCount(){var n=0;for(var k in selected)if(selected[k])n++;return n;}
  function updSel(){var n=selectedCount();selCountEl.textContent='المحدد: '+n;
    document.getElementById('scSel').textContent=n;}

  function filtered(){
    var q=qEl.value.trim().toLowerCase(),t=typeSel.value;
    return docs.filter(function(d){
      if(t&&d.doc_type!==t)return false;
      if(!q)return true;
      return (d.title||'').toLowerCase().indexOf(q)>=0||(d.full_text||'').toLowerCase().indexOf(q)>=0;
    });
  }

  function renderList(){
    var fs=filtered();lastQ=qEl.value.trim();
    countEl.textContent=fs.length+' مستند مطابق';
    document.getElementById('scMatch').textContent=fs.length;
    document.getElementById('scAll').textContent=docs.length;
    listEl.innerHTML='';
    fs.forEach(function(d){
      var div=document.createElement('div');div.className='item'+(current&&current.id===d.id?' active':'');
      var cb=document.createElement('input');cb.type='checkbox';cb.checked=!!selected[d.id];
      cb.onclick=function(ev){ev.stopPropagation();selected[d.id]=cb.checked;updSel();};
      var body=document.createElement('div');
      body.innerHTML='<div class="t">'+esc(d.title)+'</div>'+
                     '<div class="s">'+esc(d.doc_type)+(d.card&&d.card['التاريخ']?' · '+esc(d.card['التاريخ']):'')+'</div>';
      body.onclick=function(){current=d;renderDetail(d);highlight();};
      div.appendChild(cb);div.appendChild(body);listEl.appendChild(div);
    });
    if(!fs.length)listEl.innerHTML='<div class="empty" style="margin-top:30px">لا نتائج.</div>';
  }
  function highlight(){
    var items=listEl.querySelectorAll('.item');
    var fs=filtered();
    items.forEach(function(el,i){el.classList.toggle('active',current&&fs[i]&&fs[i].id===current.id);});
  }

  function chips(arr){if(!arr||!arr.length)return '';
    return '<div class="chips">'+arr.map(function(x){return '<span>'+esc(x)+'</span>';}).join('')+'</div>';}

  function renderDetail(d){
    var q=lastQ,card=d.card||{},e=d.entities||{},kv='';
    Object.keys(card).forEach(function(k){if(card[k])kv+='<b>'+esc(k)+'</b><div>'+esc(card[k])+'</div>';});
    var ent='';
    function row(label,arr){if(arr&&arr.length)ent+='<div style="margin-top:6px"><b style="color:var(--mut)">'+label+':</b>'+chips(arr)+'</div>';}
    row('الأطراف',e.parties);row('أطراف آخرون',e.other_actors);row('الشركة',e.company);
    row('أرقام القضايا',e.case_numbers);row('أرقام الصكوك',e.deed_numbers_known);
    row('تواريخ هجرية',e.hijri_dates);row('تواريخ ميلادية',e.greg_dates);
    row('مبالغ',e.amounts);row('محاكم',e.courts);row('أنظمة',e.law_names);row('مواد',e.articles);
    detailEl.innerHTML=
      '<div class="card"><h2>'+esc(d.title)+'</h2><div class="kv">'+kv+'</div>'+
        (d.parent_path?'<div style="margin-top:8px;color:var(--mut);font-size:12.5px">المسار: '+esc(d.parent_path)+'</div>':'')+
        (d.viewUrl?'<div style="margin-top:6px"><a class="openlink" href="'+esc(d.viewUrl)+'" target="_blank">فتح المستند الأصلي في Google Drive ↗</a></div>':'')+
        ent+'</div>'+
      '<div class="card" style="padding:0"><div style="padding:10px 16px;border-bottom:1px solid var(--line);font-weight:600">النص الكامل</div>'+
        '<div class="txt">'+hi(d.full_text||'(لا يوجد نص مستخرج)',q)+'</div></div>';
    detailEl.scrollTop=0;
  }

  var qt;qEl.oninput=function(){clearTimeout(qt);qt=setTimeout(function(){renderList();if(current)renderDetail(current);},150);};
  typeSel.onchange=renderList;
  document.getElementById('selAll').onclick=function(){filtered().forEach(function(d){selected[d.id]=true;});updSel();renderList();};
  document.getElementById('selNone').onclick=function(){selected={};updSel();renderList();};
  renderList();updSel();

  /* ===== تحكّم الخط (محفوظ) ===== */
  var FS=14.5,LH=1.85;
  function applyFont(){var r=document.documentElement.style;
    r.setProperty('--tsize',FS+'px');r.setProperty('--tlh',LH);
    r.setProperty('--tfam',document.getElementById('fFam').value);
    r.setProperty('--talign',document.getElementById('fJustify').checked?'justify':'start');
    try{localStorage.setItem('viewerFont',JSON.stringify({FS:FS,LH:LH,fam:document.getElementById('fFam').value,j:document.getElementById('fJustify').checked}));}catch(e){}
  }
  try{var sv=JSON.parse(localStorage.getItem('viewerFont')||'null');
    if(sv){FS=sv.FS||FS;LH=sv.LH||LH;document.getElementById('fFam').value=sv.fam||'inherit';document.getElementById('fJustify').checked=!!sv.j;}}catch(e){}
  document.getElementById('fPlus').onclick=function(){FS=Math.min(26,FS+1);applyFont();};
  document.getElementById('fMinus').onclick=function(){FS=Math.max(11,FS-1);applyFont();};
  document.getElementById('lPlus').onclick=function(){LH=Math.min(2.6,Math.round((LH+0.1)*10)/10);applyFont();};
  document.getElementById('lMinus').onclick=function(){LH=Math.max(1.2,Math.round((LH-0.1)*10)/10);applyFont();};
  document.getElementById('fFam').onchange=applyFont;
  document.getElementById('fJustify').onchange=applyFont;
  applyFont();

  /* ===== التصدير ===== */
  var modal=document.getElementById('exportModal');
  document.getElementById('exportBtn').onclick=function(){updSel();modal.classList.add('open');};
  document.getElementById('exportClose').onclick=function(){modal.classList.remove('open');};
  modal.onclick=function(e){if(e.target===modal)modal.classList.remove('open');};

  function scopeDocs(){
    var s=document.querySelector('input[name=scope]:checked').value;
    if(s==='all')return docs;
    if(s==='match')return filtered();
    return docs.filter(function(d){return selected[d.id];});
  }
  function buildHTML(list,incText){
    var p=['<!DOCTYPE html><html lang="ar" dir="rtl"><head><meta charset="utf-8"><title>تصدير مستندات القضية '+
      esc(C.case_number||'')+'</title><style>',
      'body{font-family:Tahoma,Arial,sans-serif;color:#111;margin:24px;line-height:1.8}',
      'h1{font-size:20px}h2{font-size:16px;margin:0 0 6px}',
      '.note{background:#fde68a;color:#7c2d12;padding:6px 10px;border-radius:6px;font-size:12.5px;display:inline-block}',
      '.doc{border:1px solid #ddd;border-radius:10px;padding:14px 16px;margin:14px 0}',
      '.doc+.doc{page-break-before:always}',
      'table{border-collapse:collapse;margin:6px 0}td,th{border:1px solid #ccc;padding:4px 8px;font-size:13px;text-align:start}',
      'th{background:#eef}.txt{white-space:pre-wrap;word-break:break-word;font-size:13.5px;border-top:1px solid #eee;margin-top:8px;padding-top:8px}',
      'a{color:#1d4ed8}@media print{.noprint{display:none}.note{-webkit-print-color-adjust:exact;print-color-adjust:exact}}',
      '</style></head><body>',
      '<div class="noprint" style="margin-bottom:10px"><button onclick="window.print()" style="padding:8px 16px;font-size:14px;cursor:pointer">🖨️ اطبع / احفظ PDF</button></div>',
      '<h1>مستندات القضية '+esc(C.case_number||'')+' — عدد: '+list.length+'</h1>',
      '<p class="note">مخرج آلي يحتاج مراجعة بشرية — ليس رأياً قانونياً نهائياً · وُلِّد '+esc(C.generated||'')+'</p>'];
    list.forEach(function(d){
      var card=d.card||{},kv='';
      Object.keys(card).forEach(function(k){if(card[k])kv+='<tr><th>'+esc(k)+'</th><td>'+esc(card[k])+'</td></tr>';});
      p.push('<div class="doc"><h2>'+esc(d.title)+'</h2>');
      p.push('<div style="color:#666;font-size:12px">'+esc(d.doc_type)+(d.parent_path?' · '+esc(d.parent_path):'')+'</div>');
      if(kv)p.push('<table>'+kv+'</table>');
      if(d.viewUrl)p.push('<div><a href="'+esc(d.viewUrl)+'">الرابط السحابي للمستند الأصلي ↗</a></div>');
      if(incText)p.push('<div class="txt">'+esc(d.full_text||'(لا يوجد نص مستخرج)')+'</div>');
      p.push('</div>');
    });
    p.push('</body></html>');return p.join('');
  }
  function dl(name,content,mime){var b=new Blob([content],{type:mime});var u=URL.createObjectURL(b);
    var a=document.createElement('a');a.href=u;a.download=name;document.body.appendChild(a);a.click();
    document.body.removeChild(a);setTimeout(function(){URL.revokeObjectURL(u);},1500);}
  function csvCell(s){s=(s==null?'':String(s));return '"'+s.replace(/"/g,'""')+'"';}

  document.getElementById('doPrint').onclick=function(){
    var list=scopeDocs();if(!list.length){alert('لا مستندات في هذا النطاق.');return;}
    var w=window.open('','_blank');
    if(!w){alert('المتصفّح منع النافذة المنبثقة. اسمح بها أو استخدم «تنزيل HTML».');return;}
    w.document.open();w.document.write(buildHTML(list,document.getElementById('incText').checked));w.document.close();
    modal.classList.remove('open');
  };
  document.getElementById('doHtml').onclick=function(){
    var list=scopeDocs();if(!list.length){alert('لا مستندات في هذا النطاق.');return;}
    dl('مستندات_القضية_'+(C.case_number||'')+'.html',buildHTML(list,document.getElementById('incText').checked),'text/html;charset=utf-8');
    modal.classList.remove('open');
  };
  function buildWord(list,incText){
    var w=['<html xmlns:o="urn:schemas-microsoft-com:office:office" xmlns:w="urn:schemas-microsoft-com:office:word" xmlns="http://www.w3.org/TR/REC-html40">',
      '<head><meta http-equiv="Content-Type" content="text/html; charset=utf-8">',
      '<!--[if gte mso 9]><xml><w:WordDocument><w:View>Print</w:View><w:Zoom>100</w:Zoom><w:DoNotOptimizeForBrowser/></w:WordDocument></xml><![endif]-->',
      '<style>@page{size:A4;margin:2cm}body{font-family:"Arial";font-size:12pt;direction:rtl;text-align:right}',
      'h1{font-size:16pt}h2{font-size:13pt;margin:0 0 4pt}',
      'table{border-collapse:collapse;margin:4pt 0}td,th{border:1px solid #999;padding:3pt 6pt;font-size:10.5pt;text-align:right}',
      'th{background:#eef}.txt{white-space:pre-wrap;font-size:11pt;margin-top:6pt}',
      '.brk{page-break-before:always}.note{color:#7c2d12}</style></head><body dir="rtl" lang="ar">',
      '<h1>مستندات القضية '+esc(C.case_number||'')+' — عدد: '+list.length+'</h1>',
      '<p class="note">مخرج آلي يحتاج مراجعة بشرية — ليس رأياً قانونياً نهائياً · وُلِّد '+esc(C.generated||'')+'</p>'];
    list.forEach(function(d,i){
      var card=d.card||{},kv='';
      Object.keys(card).forEach(function(k){if(card[k])kv+='<tr><th>'+esc(k)+'</th><td>'+esc(card[k])+'</td></tr>';});
      w.push('<div'+(i>0?' class="brk"':'')+'><h2>'+esc(d.title)+'</h2>');
      w.push('<p style="color:#666;font-size:10pt;margin:0 0 4pt">'+esc(d.doc_type)+(d.parent_path?' · '+esc(d.parent_path):'')+'</p>');
      if(kv)w.push('<table>'+kv+'</table>');
      if(d.viewUrl)w.push('<p><a href="'+esc(d.viewUrl)+'">الرابط السحابي للمستند الأصلي</a></p>');
      if(incText)w.push('<div class="txt">'+esc(d.full_text||'(لا يوجد نص مستخرج)')+'</div>');
      w.push('</div>');
    });
    w.push('</body></html>');return w.join('');
  }
  document.getElementById('doWord').onclick=function(){
    var list=scopeDocs();if(!list.length){alert('لا مستندات في هذا النطاق.');return;}
    dl('مستندات_القضية_'+(C.case_number||'')+'.doc',buildWord(list,document.getElementById('incText').checked),'application/msword');
    modal.classList.remove('open');
  };
  document.getElementById('doCsv').onclick=function(){
    var list=scopeDocs();if(!list.length){alert('لا مستندات في هذا النطاق.');return;}
    var head=['العنوان','النوع','التاريخ','الأطراف','الجهة','رقم القضية','رقم الصك','المسار','الرابط السحابي'];
    var lines=['﻿'+head.map(csvCell).join(',')];
    list.forEach(function(d){var c=d.card||{};
      lines.push([d.title,d.doc_type,c['التاريخ']||'',c['الأطراف']||'',c['الجهة المصدِرة']||c['الجهة']||'',
        c['رقم القضية']||'',c['رقم الصك/الحكم']||c['رقم الصك']||'',d.parent_path||'',d.viewUrl||''].map(csvCell).join(','));});
    dl('بطاقات_القضية_'+(C.case_number||'')+'.csv',lines.join('\r\n'),'text/csv;charset=utf-8');
    modal.classList.remove('open');
  };

  /* ===== جداول التبويبات ===== */
  var tableView=document.getElementById('tableView'),docsView=document.getElementById('docsView');
  function showTable(key){
    var t=(C.tables||{})[key];
    if(!t){tableView.innerHTML='<div class="empty" style="margin-top:40px">لا يوجد جدول لهذا القسم.</div>';return;}
    var h='<table><thead><tr>'+t.header.map(function(x){return '<th>'+esc(x)+'</th>';}).join('')+'</tr></thead><tbody>';
    t.rows.forEach(function(r){h+='<tr>'+r.map(function(x){return '<td>'+esc(x)+'</td>';}).join('')+'</tr>';});
    tableView.innerHTML=h+'</tbody></table>';
  }
  document.querySelectorAll('.tab').forEach(function(tab){
    tab.onclick=function(){
      document.querySelectorAll('.tab').forEach(function(x){x.classList.remove('active');});
      tab.classList.add('active');
      var v=tab.getAttribute('data-view');
      if(v==='docs'){docsView.style.display='';tableView.style.display='none';}
      else{docsView.style.display='none';tableView.style.display='';showTable(v);}
    };
  });
})();
</script>
</body>
</html>
"""

if __name__ == "__main__":
    main()
