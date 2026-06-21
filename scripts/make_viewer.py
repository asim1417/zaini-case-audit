#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
make_viewer.py — توليد واجهة تصفّح أمامية (HTML) لمخرجات الفحص.

ينتج مجلد viewer/ فيه:
  - case_data.js : بيانات القضية (مستندات + جداول) مضمّنة كـ window.CASE
  - index.html   : واجهة عربية للبحث والتصفّح وعرض النص الكامل

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
        --accent:#2563eb;--accent2:#eff6ff;--warn:#fde68a;--chip:#f1f5f9;}
  *{box-sizing:border-box}
  body{margin:0;font-family:"Segoe UI",Tahoma,Arial,sans-serif;background:var(--bg);
       color:var(--ink);font-size:15px;line-height:1.7}
  header{background:var(--pane);border-bottom:1px solid var(--line);padding:10px 16px;
         display:flex;gap:12px;align-items:center;flex-wrap:wrap;position:sticky;top:0;z-index:5}
  header h1{font-size:17px;margin:0}
  .banner{background:var(--warn);color:#7c2d12;font-size:12.5px;padding:4px 10px;border-radius:6px}
  .meta{color:var(--mut);font-size:12.5px;margin-inline-start:auto}
  .wrap{display:flex;height:calc(100vh - 53px)}
  .side{width:360px;min-width:280px;background:var(--pane);border-inline-start:1px solid var(--line);
        display:flex;flex-direction:column}
  .controls{padding:10px;border-bottom:1px solid var(--line)}
  .controls input,.controls select{width:100%;padding:8px 10px;border:1px solid var(--line);
        border-radius:8px;font-size:14px;margin-bottom:6px;font-family:inherit}
  .count{font-size:12px;color:var(--mut);padding:2px 4px}
  .list{overflow:auto;flex:1}
  .item{padding:9px 12px;border-bottom:1px solid var(--line);cursor:pointer}
  .item:hover{background:var(--accent2)}
  .item.active{background:var(--accent2);border-inline-start:3px solid var(--accent)}
  .item .t{font-size:13.5px;font-weight:600;word-break:break-word}
  .item .s{font-size:11.5px;color:var(--mut);margin-top:2px}
  .tag{display:inline-block;background:var(--chip);color:#334155;border-radius:20px;
       padding:1px 9px;font-size:11px;margin-inline-start:4px}
  main{flex:1;overflow:auto;padding:18px 22px}
  .tabs{display:flex;gap:6px;flex-wrap:wrap;margin-bottom:14px}
  .tab{padding:6px 14px;border:1px solid var(--line);background:var(--pane);border-radius:20px;
       cursor:pointer;font-size:13px}
  .tab.active{background:var(--accent);color:#fff;border-color:var(--accent)}
  .card{background:var(--pane);border:1px solid var(--line);border-radius:12px;padding:14px 16px;margin-bottom:14px}
  .card h2{margin:0 0 8px;font-size:16px}
  .kv{display:grid;grid-template-columns:140px 1fr;gap:4px 12px;font-size:13.5px}
  .kv b{color:var(--mut);font-weight:600}
  .chips span{display:inline-block;background:var(--accent2);color:#1e40af;border-radius:16px;
       padding:2px 10px;font-size:12px;margin:2px}
  .txt{white-space:pre-wrap;word-break:break-word;background:var(--pane);border:1px solid var(--line);
       border-radius:12px;padding:14px 16px;font-size:14.5px;max-height:none}
  mark{background:#fde68a}
  .empty{color:var(--mut);text-align:center;margin-top:60px}
  table{border-collapse:collapse;width:100%;font-size:13px;background:var(--pane)}
  th,td{border:1px solid var(--line);padding:6px 9px;text-align:start;vertical-align:top}
  th{background:var(--accent2);position:sticky;top:0}
  a{color:var(--accent)}
  .openlink{font-size:12.5px}
  @media(max-width:760px){.wrap{flex-direction:column;height:auto}.side{width:auto}main{height:auto}}
</style>
</head>
<body>
<header>
  <h1>واجهة تصفّح القضية</h1>
  <span class="banner">مخرج آلي يحتاج مراجعة بشرية — ليس رأياً قانونياً نهائياً</span>
  <span class="meta" id="meta"></span>
</header>

<div class="tabs" style="padding:10px 16px 0">
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
      <div class="count" id="count"></div>
    </div>
    <div class="list" id="list"></div>
  </aside>
  <main id="detail"><div class="empty">اختر مستنداً من القائمة لعرض بطاقته ونصّه الكامل.</div></main>
</div>

<div id="tableView" style="display:none;padding:0 16px 30px"></div>

<script src="case_data.js"></script>
<script>
(function(){
  var C = window.CASE || {docs:[],tables:{}};
  var docs = C.docs || [];
  document.getElementById('meta').textContent =
    'القضية ' + (C.case_number||'') + ' — ' + (C.doc_count||docs.length) + ' مستند — وُلِّد ' + (C.generated||'');

  // populate type filter
  var typeSel = document.getElementById('type');
  var types = {};
  docs.forEach(function(d){types[d.doc_type]=(types[d.doc_type]||0)+1;});
  Object.keys(types).sort().forEach(function(t){
    var o=document.createElement('option');o.value=t;o.textContent=t+' ('+types[t]+')';typeSel.appendChild(o);
  });

  var listEl=document.getElementById('list'),detailEl=document.getElementById('detail'),
      qEl=document.getElementById('q'),countEl=document.getElementById('count');
  var current=null, lastQ='';

  function esc(s){return (s||'').replace(/[&<>]/g,function(c){return{'&':'&amp;','<':'&lt;','>':'&gt;'}[c];});}
  function hi(s,q){s=esc(s);if(!q)return s;
    try{return s.replace(new RegExp('('+q.replace(/[.*+?^${}()|[\]\\]/g,'\\$&')+')','gi'),'<mark>$1</mark>');}catch(e){return s;}}

  function filtered(){
    var q=qEl.value.trim().toLowerCase(), t=typeSel.value;
    return docs.filter(function(d){
      if(t && d.doc_type!==t) return false;
      if(!q) return true;
      return (d.title||'').toLowerCase().indexOf(q)>=0 || (d.full_text||'').toLowerCase().indexOf(q)>=0;
    });
  }

  function renderList(){
    var fs=filtered();lastQ=qEl.value.trim();
    countEl.textContent=fs.length+' مستند مطابق';
    listEl.innerHTML='';
    fs.forEach(function(d){
      var div=document.createElement('div');div.className='item'+(current&&current.id===d.id?' active':'');
      div.innerHTML='<div class="t">'+esc(d.title)+'</div>'+
                    '<div class="s">'+esc(d.doc_type)+(d.card&&d.card['التاريخ']?' · '+esc(d.card['التاريخ']):'')+'</div>';
      div.onclick=function(){current=d;renderDetail(d);renderList();};
      listEl.appendChild(div);
    });
    if(!fs.length) listEl.innerHTML='<div class="empty" style="margin-top:30px">لا نتائج.</div>';
  }

  function chips(arr){if(!arr||!arr.length)return '';
    return '<div class="chips">'+arr.map(function(x){return '<span>'+esc(x)+'</span>';}).join('')+'</div>';}

  function renderDetail(d){
    var q=lastQ;
    var card=d.card||{}, e=d.entities||{};
    var kv='';
    Object.keys(card).forEach(function(k){ if(card[k]) kv+='<b>'+esc(k)+'</b><div>'+esc(card[k])+'</div>'; });
    var ent='';
    function row(label,arr){ if(arr&&arr.length) ent+='<div style="margin-top:6px"><b style="color:var(--mut)">'+label+':</b>'+chips(arr)+'</div>'; }
    row('الأطراف',e.parties);row('أطراف آخرون',e.other_actors);row('الشركة',e.company);
    row('أرقام القضايا',e.case_numbers);row('أرقام الصكوك',e.deed_numbers_known);
    row('تواريخ هجرية',e.hijri_dates);row('تواريخ ميلادية',e.greg_dates);
    row('مبالغ',e.amounts);row('محاكم',e.courts);row('أنظمة',e.law_names);row('مواد',e.articles);

    detailEl.innerHTML=
      '<div class="card"><h2>'+esc(d.title)+'</h2>'+
        '<div class="kv">'+kv+'</div>'+
        (d.parent_path?'<div style="margin-top:8px;color:var(--mut);font-size:12.5px">المسار: '+esc(d.parent_path)+'</div>':'')+
        (d.viewUrl?'<div style="margin-top:6px"><a class="openlink" href="'+esc(d.viewUrl)+'" target="_blank">فتح المستند الأصلي في Google Drive ↗</a></div>':'')+
        ent+
      '</div>'+
      '<div class="card" style="padding:0"><div style="padding:10px 16px;border-bottom:1px solid var(--line);font-weight:600">النص الكامل</div>'+
        '<div class="txt">'+hi(d.full_text||'(لا يوجد نص مستخرج)',q)+'</div></div>';
    detailEl.scrollTop=0;
  }

  var qt; qEl.oninput=function(){clearTimeout(qt);qt=setTimeout(function(){renderList();if(current)renderDetail(current);},150);};
  typeSel.onchange=renderList;
  renderList();

  // ---- table views ----
  var tableView=document.getElementById('tableView'), docsView=document.getElementById('docsView');
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
