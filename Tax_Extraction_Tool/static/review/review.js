/* Drake Review — Upload → Analyze → Drake modules (one screen per form, Next/Previous) → Summary → Transfer */
pdfjsLib.GlobalWorkerOptions.workerSrc = document.querySelector('script[src*="cdnjs"]') ? "https://cdnjs.cloudflare.com/ajax/libs/pdf.js/3.11.174/pdf.worker.min.js" : "/static/vendor/pdfjs/pdf.worker.min.js";
const $ = s => document.querySelector(s);
const $$ = s => [...document.querySelectorAll(s)];
const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const isBlank = v => v === '' || v === null || v === undefined;
const STATES = 'AL AK AZ AR CA CO CT DE DC FL GA HI ID IL IN IA KS KY LA ME MD MA MI MN MS MO MT NE NV NH NJ NM NY NC ND OH OK OR PA RI SC SD TN TX UT VT VA WA WV WI WY AS GU MP PR VI'.split(' ');
const W2CODES = 'A B C D E F G H J K L M N P Q R S T V W Y Z AA BB DD EE FF GG HH II'.split(' ');
const IDENT = new Set(['Ownership','Payer','Recipient','Employer','Employee','Lender','Borrower','Trustee','Participant','School','Student','Filer','Payee','Winner',
  'Partnership','Partner','Corporation','Shareholder','Beneficiary','Policy','Issuer','Taxpayer','Spouse','Address','Source']);

const S = { sid:null, sess:null, view:null, module:null, docId:null, tab:'screen', pdf:null, pdfSid:null, page:1, zoom:1, fit:'form',
  boxes:{}, hover:null, pick:null, pending:{}, saveT:null, trT:null, jobT:null, drake:null, drakeT:null };
const store = { get(k,d){ try{ const v=localStorage.getItem('drv.'+k); return v===null?d:v; }catch(e){ return d; } }, set(k,v){ try{ localStorage.setItem('drv.'+k,v); }catch(e){} } };

async function api(url, opts={}){
  try{
    const r = await fetch(url, {headers: opts.body instanceof FormData ? {} : {'Content-Type':'application/json'}, ...opts});
    let j; try{ j = await r.json(); }catch(e){ j = {success:false, error:`Server returned HTTP ${r.status}`}; }
    if(j && typeof j==='object') j.httpStatus = r.status;
    if(r.status===404 && j && j.success!==true && !j.error) j.error = 'Not found — restart python app.py so the server has the new /review routes.';
    return j;
  }catch(e){ return {success:false, offline:true, error:'Cannot reach the app server ('+e.message+'). Is python app.py running?'}; }
}
function toast(msg, ms=2800){ const t=$('#toast'); t.textContent=msg; t.style.display='block'; clearTimeout(toast._t); toast._t=setTimeout(()=>t.style.display='none', ms); }
function modal(title, sub, body, foot){ $('#mTitle').textContent=title; $('#mSub').textContent=sub||''; $('#mBody').innerHTML=body; $('#mFoot').innerHTML=foot||''; $('#scrim').style.display='flex'; }
function closeModal(){ $('#scrim').style.display='none'; }
$('#mClose').onclick = closeModal;

/* ============================================================ data helpers */
const A = () => S.sess.analysis;
const docs = () => A().documents;
const docById = id => docs().find(d=>d.id===id);
const curDoc = () => docById(S.docId);
const stOf = id => S.sess.state[id];
const statusOf = id => S.sess.statuses[id] || {};
const vOf = (d, k) => (stOf(d.id).values[k] || {value:'', origin:'blank', src:null, confirmed:false});
const fieldOf = (d, k) => d.fields.find(f=>f.key===k);
const pdfFieldOf = (d, id) => d.pdf_fields.find(p=>p.id===id);
const linkOf = (d, k) => ((S.sess.links[d.screen] || {})[k] || {});
const MONEY = v => { const n = parseFloat(String(v).replace(/[^\d.\-]/g,'')); return isNaN(n) ? '' : n.toFixed(2); };
function drakeFormat(type, v){
  if(v===true || v===false) return v;
  const s = isBlank(v) ? '' : String(v).trim(); if(!s) return '';
  if(type==='money') return MONEY(s);
  if(type==='ssn' || type==='ein' || type==='tin'){ const d = s.replace(/\D/g,''); return d.length===9 ? d : s.toUpperCase(); }
  if(type==='zip') return s.replace(/[^\d-]/g,'');
  if(type==='date'){ const m = s.match(/^(\d{1,2})[\/-](\d{1,2})[\/-](\d{2,4})$/); if(m) return `${m[1].padStart(2,'0')}/${m[2].padStart(2,'0')}/${m[3].length===2?'20'+m[3]:m[3]}`; return s; }
  if(type==='account') return s;
  return s.toUpperCase();
}
function normalizeTyped(type, raw){
  const t = String(raw ?? '').trim(); if(!t) return '';
  if(type==='money') return /^\(?-?\$?[\d,]*\.?\d*\)?$/.test(t) && /\d/.test(t) ? ((t.startsWith('(')||t.startsWith('-'))?'-':'') + MONEY(t.replace(/[()\-]/g,'')) : t;
  if(type==='ssn' || type==='ein' || type==='tin'){ const d = t.replace(/[\s-]/g,''); return /^\d+$/.test(d) ? d : t.toUpperCase(); }
  if(type==='zip'){ const d = t.replace(/[\s-]/g,''); return /^\d+$/.test(d) ? (d.length===9 ? d.slice(0,5)+'-'+d.slice(5) : d) : t; }
  return drakeFormat(type, t);
}
/* same rules as taxflow/validate.py format_error — used to decide on the spot whether a typed value can count as confirmed */
function fmtErr(type, v){
  if(v===true || v===false || isBlank(v)) return '';
  const s = String(v).trim();
  switch(type){
    case 'money': return /^-?\d+(\.\d{1,2})?$/.test(s) ? '' : 'Enter an amount like 1234.56';
    case 'ssn': case 'ein': case 'tin': return /^\d{9}$/.test(s) ? '' : 'Must be 9 digits';
    case 'zip': return /^\d{5}(-?\d{4})?$/.test(s) ? '' : 'ZIP must be 5 or 9 digits';
    case 'state': return STATES.includes(s.toUpperCase()) ? '' : 'Use a 2-letter state code';
    case 'date': return /^\d{2}\/\d{2}\/\d{4}$/.test(s) ? '' : 'Use MM/DD/YYYY';
    case 'year': return /^(19|20)\d\d$/.test(s) ? '' : 'Enter a 4-digit year';
    case 'int': return /^\d+$/.test(s) ? '' : 'Enter a whole number';
    case 'ts': return ['T','S','J'].includes(s) ? '' : 'Use T or S';
  }
  return '';
}
/* a masked TIN (***-**-1234) is fine for reference-only fields; it only matters for a field that goes to Drake */
const fmtErrF = (f, v) => { const e = fmtErr(f.type, v);
  return e && ['tin','ssn','ein'].includes(f.type) && /[*X]/i.test(String(v)) && !f.required && !f.aid ? '' : e; };
const show = v => v===true ? 'Checked' : v===false ? 'Not checked' : isBlank(v) ? '—' : String(v);
const fmtMoney = v => { const n = parseFloat(v); return isNaN(n) ? String(v ?? '') : n.toLocaleString('en-US',{minimumFractionDigits:2, maximumFractionDigits:2}); };
const dispVal = (type, v) => type==='money' && !isBlank(v) ? fmtMoney(v) : show(v);
const fLabel = f => (f.box ? 'Box '+f.box+' · ' : '') + f.label;
function hasVal(d, f){ const v = vOf(d, f.key); if(f.type==='bool') return v.value===true || v.origin==='edited'; return !isBlank(v.value); }
const orderedDocs = () => { const out=[]; A().modules.forEach(m=>m.docs.forEach(id=>out.push(id))); return out; };

/* ============================================================ routing + steps */
function go(h){ if(location.hash!==h) location.hash = h; else route(); }
window.addEventListener('hashchange', route);
async function route(){
  const h = location.hash.replace(/^#\/?/, '').split('/').map(decodeURIComponent);
  clearHover(); cancelPick();
  if(h[0]!=='s'){ S.sid=null; S.sess=null; return viewUpload(); }
  const sid = h[1];
  if(S.sid!==sid || !S.sess || S.sess.status==='analyzing'){ S.sid = sid; S.sess = null; await loadSession(); }
  if(!S.sess) return;
  if(S.sess.status==='analyzing') return viewAnalyzing();
  const v = h[2] || 'analyze';
  if(v==='analyze') return viewAnalysis();
  if(v==='summary') return viewSummary();
  if(v==='transfer') return viewTransfer();
  if(v==='m'){ const mod = h[3]; const m = A().modules.find(x=>x.name===mod) || A().modules[0];
    const id = (h[4] && m.docs.includes(h[4])) ? h[4] : (m.docs.find(id=>!stOf(id).reviewed && !stOf(id).excluded) || m.docs[0]);
    return viewWorkspace(m.name, id); }
  viewAnalysis();
}
async function loadSession(){
  const r = await api('/api/review/'+encodeURIComponent(S.sid));
  if(!r.success){ $('#app').innerHTML = `<div class="page"><div class="card"><div class="alert bad">${esc(r.error||'Could not load this review.')}</div><a class="btn" href="#/upload">← Back to upload</a></div></div>`; renderSteps(); return; }
  S.sess = r; $('#fileName').textContent = r.file || ''; $('#fileName').title = r.file || '';
  const tp = r.analysis && r.analysis.taxpayer;
  if(tp){ $('#tpChip').hidden=false; $('#tpChip').innerHTML = `<b>${esc(tp.name)}</b> · SSN ***-**-${esc(tp.last4)} · ${esc(r.analysis.tax_year||'')}`; } else $('#tpChip').hidden = true;
}
function moduleProgress(m){ const n = m.docs.length, done = m.docs.filter(id=>stOf(id).reviewed||stOf(id).excluded).length, err = m.docs.some(id=>(statusOf(id).errors||0)>0 && !stOf(id).excluded); return {n, done, err}; }
function renderSteps(){
  const st = []; const base = S.sid ? `#/s/${encodeURIComponent(S.sid)}` : '';
  st.push({k:'upload', label:'Upload PDF', href:'#/upload', done:!!S.sid});
  st.push({k:'analyze', label:'Analyze', href: base ? base+'/analyze' : '', done: !!(S.sess && S.sess.analysis), off:!S.sid});
  let allDone = true;
  if(S.sess && S.sess.analysis){
    A().modules.forEach(m=>{ const p = moduleProgress(m); if(p.done<p.n) allDone=false;
      st.push({k:'m:'+m.name, label:m.name, count:`${p.done}/${p.n}`, href:`${base}/m/${encodeURIComponent(m.name)}`, done:p.done===p.n, err:p.err && p.done<p.n}); });
  } else { allDone = false; st.push({k:'mods', label:'Drake modules', off:true}); }
  const tr = S.sess && S.sess.transfer;
  st.push({k:'summary', label:'Final review', href: base ? base+'/summary' : '', done: allDone && !!(S.sess&&S.sess.analysis), off:!(S.sess&&S.sess.analysis)});
  st.push({k:'transfer', label:'Transfer to Drake', href: base ? base+'/transfer' : '', done: !!(tr && tr.finished && !tr.dry_run && !tr.error), off:!(S.sess&&S.sess.analysis)});
  const cur = S.view==='workspace' ? 'm:'+S.module : S.view;
  $('#steps').innerHTML = st.map((s,i)=>`${i?'<span class="sarrow">›</span>':''}<a class="step ${s.k===cur?'cur':''} ${s.done?'done':''} ${s.err?'err':''} ${s.off?'off':''}" ${s.href?`href="${s.href}"`:''}>
     <span class="n">${s.done?'✓':s.err?'!':i+1}</span>${esc(s.label)}${s.count?` <span class="c">${s.count}</span>`:''}</a>`).join('');
}

/* ============================================================ 1. upload */
async function viewUpload(){
  S.view='upload'; renderSteps(); $('#fileName').textContent=''; $('#tpChip').hidden=true;
  $('#app').innerHTML = `<div class="page">
    <div class="card"><h2>Upload a tax packet</h2><div class="muted" style="margin-bottom:14px">Any PDF: W-2s, 1099s (INT, DIV, R, MISC, NEC, G, K, B, OID, SA, Q), SSA-1099, 1098 / 1098-T / 1098-E, 5498, 1095, K-1s and brokerage composite statements.
      Every page is analysed, each form is placed on its Drake screen, and nothing goes to Drake until you have reviewed and confirmed it.</div>
      <label class="dropzone" id="drop"><input type="file" id="fileIn" accept="application/pdf" hidden>
        <div class="big">Drop the PDF here or click to choose</div><div class="muted">The analysis starts as soon as the file is uploaded.</div></label>
      <div style="margin-top:10px"><button class="btn ghost" id="useCur">Use the packet already loaded on the W-2 page</button></div>
    </div>
    <div class="card"><h3>Recent reviews</h3><div id="recent" class="muted">Loading…</div></div></div>`;
  const drop = $('#drop'), fin = $('#fileIn');
  fin.onchange = () => fin.files[0] && upload(fin.files[0]);
  ['dragenter','dragover'].forEach(e=>drop.addEventListener(e, ev=>{ ev.preventDefault(); drop.classList.add('over'); }));
  ['dragleave','drop'].forEach(e=>drop.addEventListener(e, ev=>{ ev.preventDefault(); drop.classList.remove('over'); }));
  drop.addEventListener('drop', ev=>{ const f = ev.dataTransfer.files[0]; if(f) upload(f); });
  $('#useCur').onclick = async () => { const r = await api('/api/review/use-current', {method:'POST', body:'{}'}); if(!r.success) return toast(r.error, 5000); go(`#/s/${r.id}/analyze`); };
  const r = await api('/api/review/sessions');
  const list = (r.sessions||[]);
  $('#recent').innerHTML = !r.success ? `<div class="alert bad">${esc(r.error)}</div>` : !list.length ? 'No reviews yet.' :
    `<table class="t"><thead><tr><th>File</th><th>Taxpayer</th><th>Year</th><th>Forms</th><th>Reviewed</th><th>Updated</th><th></th></tr></thead><tbody>${list.map(s=>`
      <tr class="click" data-id="${esc(s.id)}"><td>${esc(s.file)}</td><td>${esc(s.taxpayer||'—')}</td><td>${esc(s.year||'')}</td><td>${s.documents}</td>
      <td>${s.reviewed}/${s.documents} ${s.transferred?'<span class="tag ok">sent to Drake</span>':''}</td><td class="muted">${new Date((s.updated||0)*1000).toLocaleString()}</td>
      <td>${s.status==='error'?'<span class="tag bad">failed</span>':'<span class="btn">Open →</span>'}</td></tr>`).join('')}</tbody></table>`;
  $$('#recent tr[data-id]').forEach(tr=>tr.onclick=()=>go(`#/s/${tr.dataset.id}/analyze`));
}
async function upload(file){
  if(!/\.pdf$/i.test(file.name)) return toast('Please choose a PDF file');
  $('#drop').innerHTML = `<div class="big"><span class="spinner dk"></span> Uploading ${esc(file.name)}…</div>`;
  const fd = new FormData(); fd.append('file', file);
  const r = await api('/api/review/upload', {method:'POST', body:fd});
  if(!r.success){ toast(r.error||'Upload failed', 5000); return viewUpload(); }
  go(`#/s/${r.id}/analyze`);
}

/* ============================================================ 2. analyze */
async function viewAnalyzing(){
  S.view='analyze'; renderSteps();
  $('#app').innerHTML = `<div class="page"><div class="card"><h2>Analyzing the PDF</h2><div class="muted" id="jobStage">Starting…</div><div class="prog"><i id="jobBar" style="width:3%"></i></div>
    <div class="muted">Reading every page, recognising each tax form and statement, extracting every field with its page and position.</div></div></div>`;
  clearTimeout(S.jobT);
  const poll = async () => {
    const j = await api(`/api/review/${S.sid}/job`);
    if(j.error && j.stage==='Failed'){ $('#jobStage').innerHTML = `<span class="tag bad">Failed</span> ${esc(j.error)}`; return; }
    if(j.success){ $('#jobStage').textContent = j.stage; $('#jobBar').style.width = Math.max(3, j.pct)+'%'; }
    if(j.success && j.pct>=100 && j.stage==='Done'){ await loadSession(); return route(); }
    S.jobT = setTimeout(poll, 600);
  };
  poll();
}
function viewAnalysis(){
  S.view='analyze'; renderSteps();
  const a = A(), real = a.documents.filter(d=>!d.derived);
  const byMod = a.modules.map(m=>({m, ds:m.docs.map(docById)}));
  const kindLbl = {form:'Tax form', statement:'Composite statement', supporting:'Supporting page', unknown:'Unrecognized', blank:'Blank', unclassified:'Unclassified'};
  const pageTitle = p => { const ds = p.docs.map(docById).filter(Boolean); return `Page ${p.page} · ${kindLbl[p.kind]||p.kind}${p.label?' · '+p.label:''}${ds.length?'\n'+ds.map(d=>`${d.type} — ${d.payer}`).join('\n'):''}`; };
  const flagsN = d => d.flags.filter(f=>f.level==='warn').length;
  const ext = d => { const fs = d.fields.filter(f=>f.mode!=='manual'); return `${fs.filter(f=>f.status==='extracted').length}/${fs.length}`; };
  const tileLabel = (p, d) => !d ? '' : (p.kind==='statement' && d.page!==p.page) ? '···' : d.type.replace('1099-','').replace('SSA-1099','SSA').replace('UNKNOWN','?');
  $('#app').innerHTML = `<div class="page">
   <div class="card"><h2>${esc(a.file)}</h2><div class="muted">Analysis complete — every form is placed on the Drake screen it belongs to. Review them module by module.</div>
    <div class="stats">
      <div class="stat"><div class="k">Pages</div><div class="v">${a.total_pages}</div></div>
      <div class="stat"><div class="k">Tax forms found</div><div class="v">${real.length}</div></div>
      <div class="stat"><div class="k">Drake modules</div><div class="v">${a.modules.length}</div></div>
      <div class="stat"><div class="k">Tax year</div><div class="v">${esc(a.tax_year||'?')}</div></div>
      <div class="stat"><div class="k">Taxpayer</div><div class="v" style="font-size:14px;margin-top:6px">${esc(a.taxpayer?a.taxpayer.name:'—')}${a.spouse?`<br><span class="muted">Spouse: ${esc(a.spouse.name||'***'+a.spouse.last4)}</span>`:''}</div></div>
    </div>
    <div style="display:flex;gap:10px;margin-top:12px"><button class="btn primary lg" id="startBtn">Start review → ${esc(a.modules[0]?a.modules[0].name:'')}</button>
      <button class="btn" id="reBtn" title="Run the extraction again (uses any field mappings learned since)">↻ Re-analyze</button></div>
   </div>
   <div class="card"><h3>Page map</h3><div class="pmap">${a.pages.map(p=>{ const d = p.docs.length ? docById(p.docs[0]) : null;
      return `<div class="pt ${p.kind}" title="${esc(pageTitle(p))}" data-doc="${d?esc(d.id):''}"><span class="ty">${esc(tileLabel(p, d))}</span>${p.page}</div>`; }).join('')}</div>
    <div class="legend2"><span><i style="background:#cfe0ff"></i>tax form</span><span><i style="background:#e3dcff"></i>composite brokerage statement</span><span><i style="background:#e6ecf5"></i>supporting page</span><span><i style="background:#ffe1c2"></i>not recognised — map manually</span><span><i style="background:#f4f5f7;border:1px solid #ddd"></i>blank</span></div></div>
   ${a.checks.length?`<div class="card"><h3>Packet checks</h3><ul class="checks">${a.checks.map(c=>`<li class="${c.level}">${esc(c.text)}</li>`).join('')}</ul></div>`:''}
   <div class="card"><h3>Forms by Drake module</h3>
    ${byMod.map(({m,ds})=>`<div class="mod-h"><h3>${esc(m.name)}</h3><span class="muted">${ds.length} form(s) · screens ${m.screens.map(esc).join(', ')}</span></div>
      <table class="t"><thead><tr><th>Drake screen</th><th>Form</th><th>Payer / source</th><th>Pages</th><th>Values read</th><th>Notes</th></tr></thead><tbody>
      ${ds.map(d=>`<tr class="click" data-doc="${esc(d.id)}"><td><b>${esc(d.screen||'—')}</b> <span class="muted">${d.records>1?`record ${d.record} of ${d.records}`:''}</span></td>
        <td>${esc(d.type)}${d.derived?' <span class="tag info">built from forms</span>':''}${d.composite?' <span class="tag grey">composite</span>':''}</td>
        <td>${esc(d.payer||'')}</td><td>${d.page}${d.pages.length>1?`<span class="muted"> (+${d.pages.length-1})</span>`:''}</td><td>${ext(d)}</td>
        <td>${d.duplicate_of?'<span class="tag warn">duplicate</span> ':''}${d.zero_value?'<span class="tag grey">all zero</span> ':''}${d.informational?'<span class="tag grey">informational</span> ':''}${flagsN(d)?`<span class="tag warn">${flagsN(d)} to check</span>`:''}${Object.values(d.issues||{}).filter(i=>i.level!=='warn').length?`<span class="tag bad">${Object.values(d.issues).filter(i=>i.level!=='warn').length} to fix</span>`:''}</td></tr>`).join('')}
      </tbody></table>`).join('')}
    ${a.absent_modules.length?`<p class="muted" style="margin-top:14px">No forms for: ${a.absent_modules.map(esc).join(', ')}.</p>`:''}
   </div></div>`;
  const openDoc = id => { const d = docById(id); if(d) go(`#/s/${S.sid}/m/${encodeURIComponent(d.module)}/${encodeURIComponent(d.id)}`); };
  $$('[data-doc]').forEach(el=>el.onclick=()=>el.dataset.doc && openDoc(el.dataset.doc));
  $('#startBtn').onclick = () => go(`#/s/${S.sid}/m/${encodeURIComponent(a.modules[0].name)}`);
  $('#reBtn').onclick = async () => { $('#reBtn').innerHTML='<span class="spinner dk"></span> Re-analyzing…'; const r = await api(`/api/review/${S.sid}/reanalyze`,{method:'POST',body:'{}'}); if(!r.success) toast(r.error,5000); await loadSession(); viewAnalysis(); };
}

/* ============================================================ 3. workspace */
function viewWorkspace(module, docId){
  const fresh = S.view!=='workspace' || !$('#rightPane');
  S.view='workspace'; S.module=module;
  if(fresh){
    $('#app').innerHTML = `<div class="ws" id="ws">
      <section class="pane" id="pdfPane"><div class="pdfdoc" id="pdfDoc"></div>
        <div class="ptools"><button class="btn" id="prevPage">‹</button><span class="lbl" id="pageLbl">–</span><button class="btn" id="nextPage">›</button>
          <button class="btn" id="zoomOut">−</button><button class="btn" id="zoomIn">+</button><button class="btn" id="fitForm" title="Crop to this form">Form</button><button class="btn" id="fitPage" title="Whole page">Page</button></div>
        <div id="pdfScroll"><div id="pdfStage"><div id="pdfInner"><canvas id="pdfCanvas"></canvas><div id="pdfOverlay"></div></div></div></div></section>
      <div id="split"></div>
      <section class="pane" id="rightPane"><div class="dkwin">
        <div class="dktitle"><span class="ic"></span><span id="dkTitle">Drake Tax 2025 — Data Entry</span><span class="wb">─ ☐ ✕</span></div>
        <div class="dktabs" id="dkTabs"></div>
        <div class="forms" id="formChips"></div>
        <div class="rhead" id="rhead"></div>
        <div class="issues" id="issues"></div>
        <div class="flags" id="flags"></div>
        <div id="formScroll"><div id="dkWrap"><div id="dk"></div></div></div>
        <div id="mapScroll" hidden></div>
        <div id="liveWrap" hidden><img id="liveImg" alt=""></div>
      </div>
      <div class="foot" id="foot"></div></section></div>`;
    wireWorkspace();
  }
  showDoc(docId);
}
function wireWorkspace(){
  const main = $('#ws'), sp = $('#split'), apply = p => main.style.setProperty('--split', p+'%');
  apply(parseFloat(store.get('split','42'))||42);
  sp.addEventListener('pointerdown', e=>{ e.preventDefault(); sp.classList.add('drag'); sp.setPointerCapture(e.pointerId);
    const mv = ev=>{ const r = main.getBoundingClientRect(); apply(Math.min(65,Math.max(22,(ev.clientX-r.left)/r.width*100)).toFixed(1)); fitScreen(); clearHover(); };
    const up = ()=>{ sp.classList.remove('drag'); sp.removeEventListener('pointermove',mv); sp.removeEventListener('pointerup',up); store.set('split', main.style.getPropertyValue('--split').replace('%','')); renderPage(S.page); fitScreen(); drawMapArrows(); };
    sp.addEventListener('pointermove',mv); sp.addEventListener('pointerup',up); });
  $('#prevPage').onclick=()=>renderPage(S.page-1); $('#nextPage').onclick=()=>renderPage(S.page+1);
  $('#zoomIn').onclick=()=>{ S.zoom=Math.min(3,S.zoom+0.2); renderPage(S.page); }; $('#zoomOut').onclick=()=>{ S.zoom=Math.max(0.4,S.zoom-0.2); renderPage(S.page); };
  $('#fitForm').onclick=()=>{ S.fit='form'; S.zoom=1; store.set('fit','form'); renderPage(curDoc().page); };
  $('#fitPage').onclick=()=>{ S.fit='page'; S.zoom=1; store.set('fit','page'); renderPage(S.page); };
  ['#pdfScroll','#formScroll','#mapScroll'].forEach(s=>$(s).addEventListener('scroll', ()=>{ requestAnimationFrame(repositionLabels); if(s==='#mapScroll') requestAnimationFrame(drawMapArrows); }, {passive:true}));
}
async function showDoc(docId){
  const d = docById(docId); if(!d) return;
  const changed = S.docId !== docId; S.docId = docId; S.module = d.module;
  renderSteps(); renderDkTabs(); renderFormChips(); renderHead(); renderBody(); renderFoot();
  $('#dkTitle').textContent = `Drake Tax 2025 — Data Entry — ${A().taxpayer ? A().taxpayer.name : ''}${A().taxpayer?' (***-**-'+A().taxpayer.last4+')':''} — Screen ${d.screen||'—'}`;
  $('#pdfDoc').textContent = `${d.type} · ${d.payer||''} · page ${d.page}`;
  if(S.pdfSid !== S.sid){ S.pdf = null; S.pdfSid = S.sid; try{ S.pdf = await pdfjsLib.getDocument({url:`/api/review/${S.sid}/pdf`}).promise; }catch(e){ toast('Could not load the PDF: '+e.message, 6000); } }
  if(changed || !S.page) await renderPage(d.page); else drawPdfBoxes();
}
function renderDkTabs(){
  const present = new Set(A().modules.map(m=>m.name));
  const all = ['General','Income','Adjustments','Credits','Taxes','Health Care','Other Forms','Foreign','Miscellaneous','States'];
  $('#dkTabs').innerHTML = all.map(n=>{ const m = A().modules.find(x=>x.name===n); const p = m && moduleProgress(m);
    return `<div class="dktab ${n===S.module?'sel':''} ${present.has(n)?'':'none'}" data-mod="${esc(n)}" title="${present.has(n)?'':'No forms for this module in the PDF'}">${esc(n)}${p?`<span class="cnt ${p.done===p.n?'done':''}">${p.done}/${p.n}</span>`:''}</div>`; }).join('');
  $$('#dkTabs .dktab[data-mod]').forEach(t=>t.onclick=()=>{ if(present.has(t.dataset.mod)) go(`#/s/${S.sid}/m/${encodeURIComponent(t.dataset.mod)}`); });
}
function renderFormChips(){
  const m = A().modules.find(x=>x.name===S.module);
  $('#formChips').innerHTML = m.docs.map(id=>{ const d = docById(id), st = statusOf(id).state || 'pending';
    return `<div class="fchip ${id===S.docId?'sel':''}" data-id="${esc(id)}" title="${esc(d.form_name)} — ${esc(d.payer||'')} (page ${d.page}) · ${st.replace('_',' ')}">
      <span class="dot ${st}"></span><span class="sc">${esc(d.screen||'?')}</span>${esc(d.type)}${d.records>1?` <span class="muted">${d.record}/${d.records}</span>`:''} · ${esc((d.payer||'').slice(0,26))}</div>`; }).join('');
  $$('#formChips .fchip').forEach(c=>c.onclick=()=>go(`#/s/${S.sid}/m/${encodeURIComponent(S.module)}/${encodeURIComponent(c.dataset.id)}`));
  const sel = $('#formChips .fchip.sel'); if(sel) sel.scrollIntoView({block:'nearest', inline:'nearest'});
}
function renderHead(){
  const d = curDoc(), st = stOf(d.id);
  $('#rhead').innerHTML = `<span class="ttl"><span class="sc">${esc(d.screen||'—')}</span>${esc(d.screen_name)}${d.records>1?` <span class="muted" style="font-weight:500">· record ${d.record} of ${d.records}</span>`:''}</span>
    <div class="tabs"><button data-tab="screen" class="${S.tab==='screen'?'on':''}">Drake screen</button><button data-tab="map" class="${S.tab==='map'?'on':''}">Field mapping</button><button data-tab="live" class="${S.tab==='live'?'on':''}">Live Drake</button></div>
    <button class="btn on" id="hlBtn" title="Colour fields by status">Highlights</button>
    <button class="btn" id="confAll">✓ Confirm all valid</button>
    <button class="btn" id="autoBtn" title="Match every empty Drake field with an unused value from this form">⇄ Match remaining</button>
    <button class="btn ghost" id="resetBtn" title="Take every value from the PDF again">↺ Reset</button>
    ${d.screen?`<button class="btn ghost" id="linkBtn" title="Read the real Drake screen and link its fields, so more values can be entered automatically">🔗 Link Drake fields</button>`:''}
    <label class="btn ghost" title="Excluded forms are never sent to Drake"><input type="checkbox" id="exclChk" ${st.excluded?'checked':''}> Exclude</label>
    <span class="counts" id="counts" style="margin-left:auto"></span>`;
  $$('#rhead [data-tab]').forEach(b=>b.onclick=()=>{ S.tab=b.dataset.tab; renderHead(); renderBody(); });
  $('#hlBtn').classList.toggle('on', document.body.classList.contains('hl'));
  $('#hlBtn').onclick=()=>{ const on=document.body.classList.toggle('hl'); $('#hlBtn').classList.toggle('on',on); };
  $('#confAll').onclick = confirmAllValid; $('#autoBtn').onclick = autoMatch; $('#resetBtn').onclick = resetDoc;
  if($('#linkBtn')) $('#linkBtn').onclick = linkDrakeFields;
  $('#exclChk').onchange = e => { stOf(d.id).excluded = e.target.checked; save(d.id, {excluded:e.target.checked}, true); renderBody(); renderFoot(); };
}
function renderBody(){
  const d = curDoc(), st = stOf(d.id);
  $('#formScroll').hidden = S.tab!=='screen'; $('#mapScroll').hidden = S.tab!=='map'; $('#liveWrap').hidden = S.tab!=='live';
  if(S.tab!=='live') stopLive();
  $('#flags').innerHTML = d.flags.map(f=>`<div class="${f.level}">${esc(f.text)}</div>`).join(''); $('#flags').hidden = !d.flags.length;
  if(st.excluded){
    $('#issues').hidden = true;
    $('#formScroll').innerHTML = `<div class="excl-note"><b>This form is excluded</b> — it will not be sent to Drake.<br>${d.duplicate_of?'It looks like a duplicate of another form in the packet.<br>':''}${d.informational?'It is informational (Drake does not need a separate entry).<br>':''}Untick <b>Exclude</b> to review it.</div>`;
    $('#mapScroll').innerHTML = ''; updateCounts(); return;
  }
  $('#issues').hidden = false;
  if(!$('#dkWrap')) $('#formScroll').innerHTML = `<div id="dkWrap"><div id="dk"></div></div>`;
  if(S.tab==='screen'){ buildScreen(d); fitScreen(); renderValues(); paintForm(); }
  if(S.tab==='map'){ renderMap(); }
  if(S.tab==='live') startLive();
  renderIssues(); updateCounts();
}
function renderFoot(){
  const d = curDoc(), order = orderedDocs(), i = order.indexOf(d.id), st = stOf(d.id), stt = statusOf(d.id);
  const prev = order[i-1], next = order[i+1];
  const m = A().modules.find(x=>x.name===S.module), mi = m.docs.indexOf(d.id);
  $('#foot').innerHTML = `<button class="btn" id="prevBtn" ${prev?'':'disabled'}>‹ Previous</button>
    <span class="pos">${esc(S.module)} · form ${mi+1} of ${m.docs.length} &nbsp;|&nbsp; packet ${i+1} of ${order.length}</span>
    <span class="sp"></span>
    ${st.excluded ? '<span class="tag grey">excluded</span>' : st.reviewed ? `<span class="tag ok">✓ reviewed</span> <button class="btn ghost" id="unrev">Undo</button>`
      : `<button class="btn good" id="revBtn" ${stt.errors?`title="Fix ${stt.errors} field(s) first"`:''}>✓ Mark form reviewed</button>`}
    <button class="btn primary" id="nextBtn">${next ? (docById(next).module!==S.module ? `Next: ${esc(docById(next).module)} ›` : 'Next ›') : 'Final review ›'}</button>`;
  $('#prevBtn').onclick = () => prev && goDoc(prev);
  $('#nextBtn').onclick = () => next ? goDoc(next) : go(`#/s/${S.sid}/summary`);
  if($('#revBtn')) $('#revBtn').onclick = markReviewed;
  if($('#unrev')) $('#unrev').onclick = async () => { await flushSave(); const r = await api(`/api/review/${S.sid}/doc/${d.id}`, {method:'POST', body:JSON.stringify({reviewed:false})}); applyStatus(d.id, r); renderFoot(); };
}
const goDoc = id => { const d = docById(id); go(`#/s/${S.sid}/m/${encodeURIComponent(d.module)}/${encodeURIComponent(id)}`); };

/* ---------------- saving ---------------- */
function save(docId, patch, now){
  const p = S.pending[docId] = S.pending[docId] || {values:{}};
  if(patch.values) for(const [k,v] of Object.entries(patch.values)) p.values[k] = {...(p.values[k]||{}), ...v};
  if('excluded' in patch) p.excluded = patch.excluded;
  clearTimeout(S.saveT); S.saveT = setTimeout(flushSave, now ? 0 : 350);
}
async function flushSave(){
  clearTimeout(S.saveT);
  const all = S.pending; S.pending = {};
  for(const [id, body] of Object.entries(all)){
    const r = await api(`/api/review/${S.sid}/doc/${encodeURIComponent(id)}`, {method:'POST', body:JSON.stringify(body)});
    if(r.offline){ toast(r.error, 5000); continue; }
    applyStatus(id, r);
  }
}
function applyStatus(id, r){
  if(r && r.status){ S.sess.statuses[id] = r.status; stOf(id).reviewed = r.status.reviewed; stOf(id).excluded = r.status.excluded; }
  if(S.view==='workspace' && id===S.docId){ paintForm(); renderIssues(); updateCounts(); paintPdf(); if(S.tab==='map') renderMap(); }
  if(S.view==='workspace'){ renderSteps(); renderDkTabs(); renderFormChips(); }
}
function setVal(k, patch){
  const d = curDoc(), cur = stOf(d.id).values[k] = {...vOf(d,k), ...patch};
  if('value' in patch && !('confirmed' in patch)) cur.confirmed = false;
  save(d.id, {values:{[k]: {...patch, ...( 'value' in patch && !('confirmed' in patch) ? {confirmed:false} : {})}}});
}

/* ---------------- Drake screen ---------------- */
function buildScreen(d){
  const L = window.DRAKE_LAYOUTS[d.screen];
  const used = new Set(); let h = '', W = 940, H;
  const fieldsShown = d.fields.filter(f=>f.key!=='form_variant');
  if(L){
    W = L.width; H = L.height;
    h += L.chrome;
    for(const [t,x,y,cls,end] of L.text) h += `<span class="t ${cls}" style="left:${x}px;top:${y}px;${end?`width:${end-x}px;`:''}">${esc(t)}</span>`;
    for(const [lk,kind,x,y,w] of L.boxes){
      const k = L.map[lk], f = k && fieldOf(d,k);
      if(f) used.add(k);
      h += ctlHtml(f, kind, x, y, w, L.blue && L.blue.has(lk), L.notes && L.notes[lk]);
    }
    const rest = fieldsShown.filter(f=>!used.has(f.key) && f.mode!=='manual');
    if(rest.length){ const r = genericRows(rest, H + 18, `Other values on this form (not on Drake Screen ${d.screen})`); h += r.html; H = r.bottom + 14; }
  } else {
    h += `<span class="t h1" style="left:16px;top:10px">${esc(d.form_name)}</span>`;
    h += `<div class="tab sel" style="left:0;top:-30px;width:0;border:0"></div>`;
    let y = 36;
    const ts = fieldOf(d,'ts');
    if(ts){ h += `<span class="t ts" style="left:16px;top:${y+2}px">TS</span>` + ctlHtml(ts,'cb',39,y,43); used.add('ts');
            h += `<span class="t" style="left:96px;top:${y+3}px;color:#555">T = taxpayer · S = spouse</span>`; y += 30; }
    if(!fieldsShown.filter(f=>!used.has(f.key)).length){
      h += `<div class="frame" style="left:12px;top:${y+8}px;width:916px;height:120px"></div><div class="lg" style="left:21px;top:${y+1}px">Unrecognized document</div>
        <span class="t" style="left:28px;top:${y+30}px;white-space:normal;width:880px;line-height:16px;font-size:12px">This page was not recognised as a supported tax form. Open <b>Field mapping</b> to see every value found on it,<br>or choose the form type below and map its values onto the Drake fields.</span>`;
      H = y + 140;
    } else {
      const left = [], right = [];
      const secs = []; fieldsShown.filter(f=>!used.has(f.key)).forEach(f=>{ let s = secs.find(x=>x.name===f.section); if(!s){ s={name:f.section||'Fields', fields:[]}; secs.push(s); } s.fields.push(f); });
      secs.forEach(s=>(IDENT.has(s.name) ? left : right).push(s));
      if(!left.length || !right.length){ const all = left.concat(right); left.length=0; right.length=0; let hl=0, hr=0; all.forEach(s=>{ if(hl<=hr){ left.push(s); hl+=s.fields.length; } else { right.push(s); hr+=s.fields.length; } }); }
      const col = (arr, x0, w) => { let yy = y; let out=''; for(const s of arr){ const r = sectionHtml(s, x0, yy, w); out += r.html; yy = r.bottom + 14; } return {html:out, bottom:yy}; };
      const a = col(left, 12, 452), b = col(right, 476, 452);
      h += a.html + b.html; H = Math.max(a.bottom, b.bottom) + 6;
    }
    H = Math.max(H, 300);
  }
  h += `<div class="bottomline" style="top:${H-12}px"></div>`;
  $('#dk').innerHTML = h; $('#dk').style.width = W+'px'; $('#dk').style.height = H+'px'; $('#dk').dataset.w = W; $('#dk').dataset.h = H;
  bindInputs();
}
function sectionHtml(s, x, y, w){
  let h = '', yy = y + 14;
  for(const f of s.fields){ h += rowHtml(f, x, yy, w); yy += f.type==='bool' ? 18 : 21; }
  const height = yy - y + 4;
  return {html: `<div class="frame" style="left:${x}px;top:${y+6}px;width:${w}px;height:${height}px"></div><div class="lg" style="left:${x+9}px;top:${y}px">${esc(s.name)}</div>` + h, bottom: y + 6 + height};
}
function genericRows(fields, y, title){
  const secs=[{name:title, fields}]; let out='', yy=y;
  const half = Math.ceil(fields.length/2), a = {name:title, fields:fields.slice(0,half)}, b = {name:'', fields:fields.slice(half)};
  const r1 = sectionHtml(a, 12, yy, 452), r2 = b.fields.length ? sectionHtml(b, 476, yy, 452) : {html:'', bottom:yy};
  void secs; out = r1.html + r2.html; return {html: out, bottom: Math.max(r1.bottom, r2.bottom)};
}
const WIDTH = {money:110, ssn:100, ein:100, tin:100, zip:80, state:54, date:90, year:50, int:60, percent:60, code:54, ts:43, account:150, text:270, name:270};
function rowHtml(f, x, y, w){
  if(f.type==='bool'){ return `<span class="fl" style="left:${x+10}px;top:${y+1}px"><span class="bx">${esc(f.box)}</span></span>${ctlHtml(f,'ck',x+34,y)}<span class="fl" style="left:${x+52}px;top:${y+1}px;max-width:${w-60}px;overflow:hidden" title="${esc(f.label)}">${esc(f.label)}</span>`; }
  const iw = Math.min(WIDTH[f.type] || 200, w - 150), ix = x + w - iw - 10;
  const kind = (f.type==='state' || f.type==='ts' || (f.type==='code' && f.control==='combo')) ? 'cb' : 'in';
  return `<span class="fl" style="left:${x+10}px;top:${y+3}px;width:${ix-x-16}px;overflow:hidden" title="${esc(fLabel(f))}"><span class="bx">${esc(f.box)}</span>${esc(f.label)}<span style="color:#666"> ......................................................................................................</span></span>` + ctlHtml(f, kind, ix, y, iw);
}
function ctlHtml(f, kind, x, y, w, blue, note){
  if(!f){   // a Drake field we do not fill from the PDF
    if(kind==='ck') return `<span class="ck ro" style="left:${x}px;top:${y}px"><input type="checkbox" disabled></span>`;
    const inner = kind==='dis' ? `<input readonly tabindex="-1" value="<Click to Access>">` : (kind==='cb'||kind==='cbd') ? `<select disabled tabindex="-1"><option></option></select>` : `<input readonly tabindex="-1">`;
    return `<span class="c ${kind==='dis'?'dis':'ro'}" style="left:${x}px;top:${y}px;width:${w}px" title="Not read from the PDF — enter in Drake if needed">${inner}</span>`;
  }
  const lk = linkOf(curDoc(), f.key), nl = !lk.aid && !f.ref ? `<span class="nolink" style="left:${x-4}px;top:${y-3}px" title="Not linked to a Drake field yet — use Link Drake fields"></span>` : '';
  if(kind==='ck') return `<span class="ck" data-k="${f.key}" style="left:${x}px;top:${y}px"><input type="checkbox"></span><span class="cfm" data-cfm="${f.key}" style="left:${x+10}px;top:${y-8}px"></span>${nl}`;
  let ctl;
  if(kind==='cb'){ const opts = f.type==='state' ? ['',...STATES] : f.type==='ts' ? ['','T','S','J'] : f.key.startsWith('box12') ? ['',...W2CODES] : (f.options && f.options.length ? f.options : ['']);
    ctl = `<select>${opts.map(o=>`<option value="${o}">${o}</option>`).join('')}</select>`; }
  else ctl = `<input spellcheck="false" autocomplete="off" class="${f.type==='money'?'amt':''}" maxlength="${f.type==='year'?4:80}">`;
  return `<span class="c ${blue?'blue':''}" ${blue?'data-blue="1"':''} data-k="${f.key}" data-note="${esc(note||'')}" style="left:${x}px;top:${y}px;width:${w}px">${ctl}</span><span class="cfm" data-cfm="${f.key}" style="left:${x+w-7}px;top:${y-6}px"></span>${nl}`;
}
const ctlOf = k => document.querySelector(`#dk [data-k="${k}"] input, #dk [data-k="${k}"] select`);
const wrapOf = k => document.querySelector(`#dk [data-k="${k}"]`);
function fitScreen(){
  const sc = $('#formScroll'), dk = $('#dk'); if(!sc || !dk || !sc.clientWidth || !dk.dataset.w) return;
  const W = +dk.dataset.w, H = +dk.dataset.h, z = Math.max(0.55, Math.min(1.7, (sc.clientWidth - 2) / W));
  dk.style.transform = `scale(${z})`; $('#dkWrap').style.width = Math.floor(W*z)+'px'; $('#dkWrap').style.height = Math.floor(H*z)+'px';
}
window.addEventListener('resize', ()=>{ clearTimeout(window._rz); window._rz = setTimeout(()=>{ if(S.view==='workspace'){ renderPage(S.page); fitScreen(); drawMapArrows(); } }, 150); });
function renderValues(){
  const d = curDoc();
  for(const f of d.fields){
    const c = ctlOf(f.key); if(!c) continue; const v = vOf(d,f.key).value;
    if(f.type==='bool') c.checked = v===true;
    else { if(c.tagName==='SELECT' && !isBlank(v) && ![...c.options].some(o=>o.value===v)) c.add(new Option(v,v)); c.value = isBlank(v) ? '' : v; }
    const w = wrapOf(f.key); if(w && w.dataset.blue!==undefined) w.classList.toggle('blue', isBlank(v));
  }
}
function bindInputs(){
  const d = curDoc();
  $$('#dk [data-k]').forEach(w=>{
    const k = w.dataset.k, f = fieldOf(d,k), c = w.querySelector('input,select'); if(!c || !f) return;
    w.addEventListener('mouseenter', ()=>hoverForm(k, w)); w.addEventListener('mouseleave', clearHover);
    w.addEventListener('contextmenu', e=>{ e.preventDefault(); clearField(k); });
    const commit = () => {
      const v = f.type==='bool' ? c.checked : normalizeTyped(f.type, c.value);
      const src = vOf(d,k).src, pf = src && pdfFieldOf(d, src);
      const pdfV = pf ? drakeFormat(f.type, pf.value) : (f.type==='bool' ? false : '');
      const origin = String(v)===String(pdfV) && pf ? 'pdf' : (f.mode==='manual' ? 'fixed' : 'edited');
      setVal(k, {value:v, origin, confirmed: !fmtErrF(f, v) && !(isBlank(v) && f.required)});   // a valid value the reviewer typed is their confirmation
      if(f.type!=='bool' && document.activeElement!==c) c.value = v;
      delete (S.results||{})[k];
    };
    c.addEventListener('change', commit);
    c.addEventListener('blur', ()=>{ if(f.type!=='bool' && c.tagName==='INPUT') c.value = isBlank(vOf(d,k).value) ? '' : vOf(d,k).value; });
    c.addEventListener('keydown', e=>{ if(e.key==='Enter'){ e.preventDefault(); c.blur(); } });
    c.addEventListener('focus', ()=>{ w.classList.remove('blue'); hoverForm(k, w, true); });
    c.addEventListener('blur', ()=>{ if(w.dataset.blue) w.classList.toggle('blue', isBlank(vOf(d,k).value)); });
  });
  $$('#dk [data-cfm]').forEach(b=>b.onclick=e=>{ e.stopPropagation(); toggleConfirm(b.dataset.cfm); });
}
function trResult(k){ const tr = S.sess.transfer; if(!tr || tr.dry_run) return null; return (tr.results||[]).find(r=>r.doc_id===S.docId && r.key===k) || null; }
function fieldState(k){
  const d = curDoc(), r = trResult(k);
  if(r) return r.status==='verified' ? 'sent' : ['failed','mismatch'].includes(r.status) ? 'failed' : null;
  const i = (statusOf(d.id).issues||{})[k]; if(i) return i.level;
  const v = vOf(d,k);
  if(v.origin==='edited' || v.origin==='mapped') return 'edited';
  if((v.origin==='pdf' || v.origin==='fixed') && !isBlank(v.value) && v.value!==false) return 'ok';
  return 'none';
}
function paintForm(){
  const d = curDoc(); if(!d || !$('#dk')) return;
  for(const f of d.fields){
    const w = wrapOf(f.key); if(!w) continue;
    w.classList.remove('s-ok','s-edited','s-missing','s-warn','s-error','s-sent','s-failed');
    const st = fieldState(f.key); if(st && st!=='none') w.classList.add('s-'+st);
    const v = vOf(d,f.key), on = !!v.confirmed, has = hasVal(d,f) || f.required;
    w.classList.toggle('conf', on);
    $$(`#dk [data-cfm="${f.key}"]`).forEach(b=>{ b.classList.toggle('show', has); b.classList.toggle('on', on); b.title = on ? 'Confirmed — will be sent to Drake. Click to un-confirm.' : 'Not confirmed — click to confirm'; });
    const i = (statusOf(d.id).issues||{})[f.key], r = trResult(f.key), lk = linkOf(d,f.key), parts = [fLabel(f)];
    if(r) parts.push('Drake: '+r.message); if(i) parts.push(i.msg); if(w.dataset.note) parts.push(w.dataset.note);
    parts.push(on ? 'Confirmed' : has ? 'Not confirmed — will NOT be sent' : '');
    parts.push(f.ref ? 'Reference only — checked against the PDF, not typed into Drake' : lk.aid ? `Drake field ${lk.aid}${lk.how==='linked'?' (linked)':''}` : 'Not linked to a Drake field yet');
    w.title = parts.filter(Boolean).join(' · ');
  }
}
function toggleConfirm(k){
  const d = curDoc(), f = fieldOf(d,k), v = vOf(d,k), i = (statusOf(d.id).issues||{})[k], e = fmtErrF(f, v.value);
  if(!v.confirmed && e) return toast(`Fix “${f.label}” first: ${e}`, 4000);
  if(!v.confirmed && i && (i.level==='error' || i.level==='missing')) return toast(`Fix “${f.label}” first: ${i.msg}`, 4000);
  setVal(k, {confirmed: !v.confirmed}); paintForm(); paintPdf(); updateCounts();
}
function confirmableKeys(){ const d = curDoc(), iss = statusOf(d.id).issues||{}; return d.fields.filter(f=>!vOf(d,f.key).confirmed && hasVal(d,f) && !iss[f.key] && !fmtErrF(f, vOf(d,f.key).value)).map(f=>f.key); }
function confirmAllValid(){
  const d = curDoc(), ks = confirmableKeys(); if(!ks.length) return toast('Nothing left to confirm automatically.');
  const vals = {}; ks.forEach(k=>{ stOf(d.id).values[k].confirmed = true; vals[k] = {confirmed:true}; });
  save(d.id, {values:vals}, true); paintForm(); paintPdf(); updateCounts();
  const left = d.fields.filter(f=>!vOf(d,f.key).confirmed && hasVal(d,f)).length;
  toast(`Confirmed ${ks.length} value(s).` + (left ? ` ${left} with a warning need your individual check.` : ''), 4000);
}
function clearField(k){
  const d = curDoc(), f = fieldOf(d,k); if(!f) return;
  setVal(k, {value: f.type==='bool' ? false : '', origin:'blank', src:null, confirmed:false});
  renderValues(); paintForm(); paintPdf(); if(S.tab==='map') renderMap(); toast(`Cleared “${f.label}” and its match`);
}
function resetDoc(){
  const d = curDoc(), vals = {};
  for(const f of d.fields){ if(f.mode==='manual') continue; const pf = pdfFieldOf(d, 'f:'+f.key);
    const v = pf && !pf.blank ? drakeFormat(f.type, pf.value) : (f.type==='bool' ? false : '');
    vals[f.key] = {value:v, origin: pf && !pf.blank ? 'pdf' : 'blank', src: pf ? pf.id : null, confirmed:false}; stOf(d.id).values[f.key] = {...vals[f.key]}; }
  save(d.id, {values:vals}, true); renderBody(); drawPdfBoxes(); toast('Every value was taken from the PDF again — confirmations cleared');
}
async function markReviewed(){
  const d = curDoc(); await flushSave();
  const r = await api(`/api/review/${S.sid}/doc/${encodeURIComponent(d.id)}`, {method:'POST', body:JSON.stringify({reviewed:true})});
  applyStatus(d.id, r);
  if(!r.success){ toast(r.error || 'Could not mark reviewed', 5000); $('#issues').classList.add('open'); renderIssues(); return; }
  renderFoot(); toast('Form reviewed ✓');
  const order = orderedDocs(), i = order.indexOf(d.id);
  const next = order.slice(i+1).find(id=>!stOf(id).reviewed && !stOf(id).excluded);
  setTimeout(()=>{ if(S.docId===d.id) next ? goDoc(next) : go(`#/s/${S.sid}/summary`); }, 450);
}
function updateCounts(){
  const d = curDoc(); if(!d || !$('#counts')) return;
  const fs = d.fields.filter(f=>f.mode!=='manual'), ext = fs.filter(f=>f.status==='extracted').length;
  const toSend = d.fields.filter(f=>hasVal(d,f)), conf = toSend.filter(f=>vOf(d,f.key).confirmed).length;
  const inputs = d.fields.filter(f=>!f.ref), linked = inputs.filter(f=>linkOf(d,f.key).aid).length;
  $('#counts').innerHTML = `Read <b>${ext}/${fs.length}</b> · Confirmed <b>${conf}/${toSend.length}</b> · Linked to Drake <b>${linked}/${inputs.length}</b>`;
  const n = confirmableKeys().length; $('#confAll').textContent = n ? `✓ Confirm all valid (${n})` : '✓ All valid confirmed'; $('#confAll').disabled = !n;
}
function renderIssues(){
  const d = curDoc(), box = $('#issues'); if(!d || !box) return; const open = box.classList.contains('open');
  const iss = statusOf(d.id).issues || {}, name = k => { const f = fieldOf(d,k); return f ? fLabel(f) : k; };
  const errs = Object.entries(iss).filter(([,i])=>i.level==='error'||i.level==='missing'), warns = Object.entries(iss).filter(([,i])=>i.level==='warn');
  const li = ([k,i]) => `<li><a href="#" data-goto="${k}">${esc(name(k))}</a>: ${esc(i.msg)}</li>`;
  if(errs.length){ box.className='issues bad'+(open?' open':''); box.innerHTML = `<b>⚠ ${errs.length} field(s) to fix before this form can be marked reviewed</b>${warns.length?` · ${warns.length} to check`:''} <span style="opacity:.7">(click to ${open?'hide':'show'})</span>${open?`<ul>${[...errs,...warns].map(li).join('')}</ul>`:''}`; }
  else if(warns.length){ box.className='issues warn'+(open?' open':''); box.innerHTML = `<b>All values are valid.</b> ${warns.length} value(s) worth a second look <span style="opacity:.7">(click to ${open?'hide':'show'})</span>${open?`<ul>${warns.map(li).join('')}</ul>`:''}`; }
  else { box.className='issues ok'; box.innerHTML = '<b>✓ All values are valid.</b> Confirm them, then mark the form reviewed.'; }
  box.querySelectorAll('[data-goto]').forEach(a=>a.onclick=e=>{ e.preventDefault(); e.stopPropagation(); if(S.tab!=='screen'){ S.tab='screen'; renderHead(); renderBody(); } const c = ctlOf(a.dataset.goto); if(c){ reveal($('#formScroll'), c); c.focus({preventScroll:true}); } });
  box.onclick = () => { box.classList.toggle('open'); renderIssues(); };
}

/* ---------------- field mapping view (arrows) ---------------- */
function renderMap(){
  const d = curDoc(), sc = $('#mapScroll');
  const srcUse = {}; d.fields.forEach(f=>{ const s = vOf(d,f.key).src; if(s) (srcUse[s] = srcUse[s] || []).push(f.key); });
  const dk = d.fields.filter(f=>f.key!=='form_variant');
  // PDF values in the order of the Drake fields they feed (keeps the arrows short), then the unused ones by position
  const rank = {}; dk.forEach((f,i)=>{ const s = vOf(d,f.key).src; if(s && !(s in rank)) rank[s] = i; });
  const pos = p => [p.page||0, (p.bbox||[0,0])[1], (p.bbox||[0])[0]];
  const pdfs = d.pdf_fields.slice().sort((a,b)=>{ const ra = a.id in rank ? rank[a.id] : 1e6, rb = b.id in rank ? rank[b.id] : 1e6;
    if(ra!==rb) return ra-rb; const pa = pos(a), pb = pos(b); return (pa[0]-pb[0]) || (pa[1]-pb[1]) || (pa[2]-pb[2]); });
  sc.innerHTML = `<div class="mapgrid" id="mapGrid">
    <div class="mcol"><h4>Values on the PDF <span class="muted" style="text-transform:none;letter-spacing:0">(${pdfs.length}) · drag onto a Drake field</span></h4>
      ${pdfs.map(p=>`<div class="mitem pdf ${p.extra?'extra':''} ${srcUse[p.id]?'used':''}" data-pdf="${esc(p.id)}" title="${esc(p.label)} — page ${p.page}${p.extra?' · not recognised automatically':''}">
        <div class="l">${esc(p.label)}<small>${p.extra?'other value on the page':'read automatically'} · p.${p.page}</small></div><div class="v">${p.blank?'<span class="muted">blank</span>':esc(dispVal(p.type, p.value))}</div></div>`).join('') || '<div class="muted">No values were found on this document.</div>'}
    </div>
    <div></div>
    <div class="mcol"><h4>Drake fields — Screen ${esc(d.screen||'—')} <button class="btn" id="autoBtn2" style="margin-left:auto">⇄ Match remaining</button></h4>
      ${dk.length ? dk.map(f=>{ const v = vOf(d,f.key), lk = linkOf(d,f.key);
        return `<div class="mitem dk ${!hasVal(d,f) && f.required?'unm':''}" data-dk="${f.key}" title="${esc(lk.aid?'Drake field '+lk.aid:'Not linked to a Drake field yet')}">
          <div class="l">${esc(fLabel(f))}<small>${v.src ? (pdfFieldOf(d,v.src)||{}).label || '' : v.origin==='edited' ? 'typed by reviewer' : v.origin==='fixed' ? 'set automatically' : 'no PDF value'}${lk.aid?'':' · <span style="color:#7c3aed">not linked</span>'}</small></div>
          <div class="v">${esc(dispVal(f.type, v.value))}${v.confirmed?' <span style="color:#15803d">✓</span>':''}</div>${v.src?`<button class="x" data-clear="${f.key}" title="Remove this match">×</button>`:''}</div>`; }).join('')
      : `<div class="alert info">This document was not recognised. Choose what it is to get its Drake screen, then drag the values across.</div>
         <select id="retype" class="btn" style="width:100%"><option value="">Choose the form type…</option>${Object.entries(S.catalog.forms).filter(([k])=>!['TAXPAYER','FOREIGN','UNKNOWN'].includes(k)).map(([k,v])=>`<option value="${esc(k)}">${esc(v.name)}</option>`).join('')}</select>`}
    </div></div><svg id="mapSvg"></svg>`;
  $$('#mapScroll .mitem.pdf').forEach(el=>{ el.onpointerdown = e => startDrag(e, el.dataset.pdf, el); el.onmouseenter = () => hoverMap(el.dataset.pdf, null); el.onmouseleave = () => hoverMap(null,null); });
  $$('#mapScroll .mitem.dk').forEach(el=>{ el.onmouseenter = () => hoverMap(null, el.dataset.dk); el.onmouseleave = () => hoverMap(null,null); });
  $$('#mapScroll [data-clear]').forEach(b=>b.onclick = e => { e.stopPropagation(); clearField(b.dataset.clear); });
  if($('#autoBtn2')) $('#autoBtn2').onclick = autoMatch;
  if($('#retype')) $('#retype').onchange = e => retype(e.target.value);
  requestAnimationFrame(drawMapArrows);
}
function drawMapArrows(){
  const svg = $('#mapSvg'), sc = $('#mapScroll'); if(!svg || sc.hidden) return;
  const d = curDoc(), g = $('#mapGrid'); svg.setAttribute('width', g.scrollWidth); svg.setAttribute('height', g.scrollHeight);
  const base = g.getBoundingClientRect(); let out = '';
  for(const f of d.fields){ const s = vOf(d,f.key).src; if(!s) continue;
    const a = sc.querySelector(`[data-pdf="${CSS.escape(s)}"]`), b = sc.querySelector(`[data-dk="${f.key}"]`); if(!a||!b) continue;
    const ra = a.getBoundingClientRect(), rb = b.getBoundingClientRect();
    const x1 = ra.right - base.left, y1 = ra.top + ra.height/2 - base.top, x2 = rb.left - base.left - 2, y2 = rb.top + rb.height/2 - base.top;
    out += `<path data-a="${esc(s)}" data-b="${f.key}" d="${arrowPath(x1,y1,x2,y2)}" marker-end="url(#ahg)"/>`; }
  svg.innerHTML = out;
}
function hoverMap(pk, k){
  $$('#mapScroll .hot').forEach(e=>e.classList.remove('hot'));
  if(pk){ $$(`#mapSvg path[data-a="${CSS.escape(pk)}"]`).forEach(p=>{ p.classList.add('hot'); const b = $(`#mapScroll [data-dk="${p.dataset.b}"]`); if(b) b.classList.add('hot'); }); }
  if(k){ $$(`#mapSvg path[data-b="${k}"]`).forEach(p=>{ p.classList.add('hot'); const a = $(`#mapScroll [data-pdf="${CSS.escape(p.dataset.a)}"]`); if(a) a.classList.add('hot'); }); }
  const d = curDoc(), src = pk || (k && vOf(d,k).src); const pf = src && pdfFieldOf(d, src);
  if(pf && pf.page){ if(pf.page!==S.page) renderPage(pf.page).then(()=>markPdfHot(pf.id)); else markPdfHot(pf.id); } else markPdfHot(null);
}
function markPdfHot(id){ $$('#pdfOverlay .fx.hot').forEach(e=>e.classList.remove('hot')); if(!id) return; const el = $(`#pdfOverlay [data-pdf-key="${CSS.escape(id)}"]`); if(el){ el.classList.add('hot'); reveal($('#pdfScroll'), el); } }
async function retype(t){
  if(!t) return; const d = curDoc();
  const r = await api(`/api/review/${S.sid}/doc/${encodeURIComponent(d.id)}/retype`, {method:'POST', body:JSON.stringify({type:t})});
  if(!r.success) return toast(r.error || 'Could not change the form type', 5000);
  await loadSession(); go(`#/s/${S.sid}/m/${encodeURIComponent(r.module)}/${encodeURIComponent(r.id)}`);
}
const toks = s => new Set(String(s||'').toLowerCase().match(/[a-z0-9]+/g) || []);
function typeOk(ft, pt){ if(ft===pt) return true; const num = ['money','int','percent'], id = ['ssn','ein','tin'];
  if(num.includes(ft)) return pt==='money'; if(id.includes(ft)) return id.includes(pt); if(['text','name','account','code','state','zip','date','year'].includes(ft)) return true; return false; }
function autoMatch(){
  const d = curDoc(), used = new Set(d.fields.map(f=>vOf(d,f.key).src).filter(Boolean)), vals = {}; let n = 0;
  for(const f of d.fields){
    if(f.mode==='manual' || hasVal(d,f)) continue;
    const own = pdfFieldOf(d, 'f:'+f.key);
    let best = null, bs = 0;
    if(own && !own.blank && !used.has(own.id)){ best = own; bs = 1; }
    else for(const p of d.pdf_fields){ if(used.has(p.id) || p.blank || isBlank(p.value) || !typeOk(f.type, p.type)) continue;
      const a = toks(fLabel(f)), b = toks(p.label); let inter = 0; a.forEach(x=>{ if(b.has(x)) inter++; });
      const s = inter / Math.max(1, new Set([...a,...b]).size) + (f.box && new RegExp(`(^|\\D)${f.box}(\\D|$)`,'i').test(p.label) ? 0.3 : 0);
      if(s > bs){ bs = s; best = p; } }
    if(best && bs >= 0.34){ used.add(best.id); const v = f.type==='bool' ? !!best.value : drakeFormat(f.type, best.value);
      vals[f.key] = {value:v, origin: best.auto===f.key ? 'pdf' : 'mapped', src:best.id, confirmed:false}; stOf(d.id).values[f.key] = {...vals[f.key]}; n++; }
  }
  if(!n) return toast('No more matches found — drag the remaining values by hand, or leave them blank.');
  save(d.id, {values:vals}, true); renderBody(); drawPdfBoxes(); toast(`Matched ${n} more field(s). Check them, then confirm ✓`, 4000);
}
function mapField(k, pk){
  const d = curDoc(), f = fieldOf(d,k), pf = pdfFieldOf(d,pk); if(!f || !pf) return;
  let v = pf.value; if(f.type==='bool') v = !!(v===true || /^(x|true|1|yes|checked)$/i.test(String(v)));
  setVal(k, {value: drakeFormat(f.type, v), origin: pf.auto===k ? 'pdf' : 'mapped', src: pk, confirmed:false});
  if(pf.extra) api(`/api/review/${S.sid}/learn`, {method:'POST', body:JSON.stringify({form_type:d.type, pdf_label:pf.label, field_key:k})});
  renderValues(); paintForm(); paintPdf(); updateCounts(); if(S.tab==='map') renderMap();
  toast(`Matched ${pf.label} → ${f.label}. Check the value, then confirm ✓` + (pf.extra ? ' (remembered for next time)' : ''), 3800);
}

/* ---------------- drag-to-map (PDF box / list item → Drake field) ---------------- */
function dropTargetAt(x, y){
  for(const el of document.elementsFromPoint(x, y)){
    const w = el.closest && (el.closest('#dk [data-k]') || el.closest('#mapScroll .mitem.dk'));
    if(w) return w;
  }
  return null;
}
const targetKey = w => w.dataset.k || w.dataset.dk;
function arrowPath(x1, y1, x2, y2){ const dx = Math.max(40, Math.abs(x2-x1)*0.45); return `M${x1},${y1} C${x1+dx},${y1} ${x2-dx},${y2} ${x2},${y2}`; }
function drawLiveArrow(fromEl, x, y){ const r = fromEl.getBoundingClientRect(); $('#arrowG').innerHTML = `<path d="${arrowPath(r.right, r.top+r.height/2, x, y)}" marker-end="url(#ah)" stroke-dasharray="6 4"/>`; }
function flashArrow(fromEl, toEl){
  const a = fromEl.getBoundingClientRect(), b = toEl.getBoundingClientRect();
  $('#arrowG').innerHTML = `<path d="${arrowPath(a.right, a.top+a.height/2, b.left-2, b.top+b.height/2)}" marker-end="url(#ah)"/>`;
  const g = $('#arrowG'); g.classList.remove('fade'); clearTimeout(S.arrowT);
  S.arrowT = setTimeout(()=>{ g.classList.add('fade'); setTimeout(()=>{ g.innerHTML=''; g.classList.remove('fade'); }, 650); }, 900);
}
function setDrop(w){ $$('.drop').forEach(e=>e!==w && e.classList.remove('drop')); if(w) w.classList.add('drop'); }
function startDrag(e, pk, el){
  if(e.button!==0) return; e.preventDefault();
  const sx=e.clientX, sy=e.clientY; let moved=false;
  const mv = ev => { if(!moved && Math.hypot(ev.clientX-sx, ev.clientY-sy) < 5) return;
    if(!moved){ moved = true; document.body.classList.add('mapping'); clearHover(); }
    drawLiveArrow(el, ev.clientX, ev.clientY); setDrop(dropTargetAt(ev.clientX, ev.clientY)); };
  const up = ev => { window.removeEventListener('pointermove', mv); window.removeEventListener('pointerup', up);
    if(!moved){ startPick(pk, el); return; }
    document.body.classList.remove('mapping'); setDrop(null);
    const w = dropTargetAt(ev.clientX, ev.clientY);
    if(w){ mapField(targetKey(w), pk); const t = wrapOf(targetKey(w)) || $(`#mapScroll [data-dk="${targetKey(w)}"]`); if(t) flashArrow(el.isConnected?el:document.body, t); } else $('#arrowG').innerHTML=''; };
  window.addEventListener('pointermove', mv); window.addEventListener('pointerup', up);
}
function startPick(pk, el){ cancelPick(); S.pick = {pk, el}; el.classList.add('picked'); document.body.classList.add('mapping'); clearHover();
  const pf = pdfFieldOf(curDoc(), pk); toast(`Now click the Drake field for “${pf ? pf.label : pk}” (Esc to cancel)`, 3500); }
function cancelPick(){ if(!S.pick) return; S.pick.el.classList.remove('picked'); S.pick=null; document.body.classList.remove('mapping'); setDrop(null); $('#arrowG').innerHTML=''; }
document.addEventListener('pointermove', e=>{ if(S.pick){ drawLiveArrow(S.pick.el, e.clientX, e.clientY); setDrop(dropTargetAt(e.clientX, e.clientY)); } });
document.addEventListener('click', e=>{
  if(!S.pick) return; if(e.target.closest('#pdfOverlay') || e.target.closest('.mitem.pdf')) return;
  const w = dropTargetAt(e.clientX, e.clientY), {pk, el} = S.pick; e.preventDefault(); e.stopPropagation();
  el.classList.remove('picked'); S.pick=null; document.body.classList.remove('mapping'); setDrop(null);
  if(w){ mapField(targetKey(w), pk); const t = wrapOf(targetKey(w)) || $(`#mapScroll [data-dk="${targetKey(w)}"]`); if(t) flashArrow(el.isConnected?el:document.body, t); } else $('#arrowG').innerHTML='';
}, true);
document.addEventListener('keydown', e=>{ if(e.key==='Escape'){ if(S.pick) cancelPick(); else if($('#scrim').style.display==='flex') closeModal(); } });

/* ---------------- PDF viewer ---------------- */
let renderTask = null;
async function renderPage(n){
  if(!S.pdf || !$('#pdfCanvas')) return;
  S.page = Math.min(Math.max(1,n), S.pdf.numPages); $('#pageLbl').textContent = `${S.page} / ${S.pdf.numPages}`;
  $('#fitForm').classList.toggle('on', S.fit==='form'); $('#fitPage').classList.toggle('on', S.fit==='page');
  const page = await S.pdf.getPage(S.page), base = page.getViewport({scale:1});
  let box = {x:0, y:0, w:base.width, h:base.height};
  const d = curDoc();
  if(S.fit==='form' && d && S.page===d.page){
    const rg = (d.regions||[]).find(r=>r.page===S.page);
    if(rg){ const m = 14; box = {x:Math.max(0,rg.x0-m), y:Math.max(0,rg.top-m), w:Math.min(base.width, rg.x1+m)-Math.max(0,rg.x0-m), h:Math.min(base.height, rg.bottom+m)-Math.max(0,rg.top-m)}; }
    else { const items = (await page.getTextContent()).items; const b = contentBox(items, base); if(b) box = b; }
  }
  const sc = $('#pdfScroll'), aw = sc.clientWidth - 16, ah = sc.clientHeight - 16;
  const k = Math.max(0.3, Math.min(aw/box.w, (S.fit==='page'?ah:1e9)/box.h, aw/box.w) * S.zoom);
  const vp = page.getViewport({scale:k}), dpr = window.devicePixelRatio || 1, cv = $('#pdfCanvas');
  if(renderTask){ try{ renderTask.cancel(); }catch(e){} }
  cv.width = Math.floor(vp.width*dpr); cv.height = Math.floor(vp.height*dpr); cv.style.width = vp.width+'px'; cv.style.height = vp.height+'px';
  $('#pdfInner').style.width = vp.width+'px'; $('#pdfInner').style.height = vp.height+'px';
  $('#pdfInner').style.left = (-box.x*k)+'px'; $('#pdfInner').style.top = (-box.y*k)+'px';
  $('#pdfStage').style.width = Math.round(box.w*k)+'px'; $('#pdfStage').style.height = Math.round(box.h*k)+'px';
  S.k = k;
  drawPdfBoxes();                       // boxes only need the scale, not the rendered image
  const task = renderTask = page.render({canvasContext: cv.getContext('2d'), viewport: vp, transform: dpr!==1?[dpr,0,0,dpr,0,0]:null});
  try{ await task.promise; }catch(e){ if(e && e.name==='RenderingCancelledException') return; console.error(e); }
}
function contentBox(items, base){
  let L=1e9,T=1e9,R=-1e9,B=-1e9;
  for(const it of items){ if(!it.str || !it.str.trim()) continue;
    const tx = pdfjsLib.Util.transform(base.transform, it.transform), fh = Math.hypot(tx[2], tx[3]);
    L=Math.min(L,tx[4]); R=Math.max(R,tx[4]+it.width); T=Math.min(T,tx[5]-fh); B=Math.max(B,tx[5]+fh*0.3); }
  if(R<=L) return null; const m = 12; L=Math.max(0,L-m); T=Math.max(0,T-m); R=Math.min(base.width,R+m); B=Math.min(base.height,B+m);
  return {x:L, y:T, w:R-L, h:B-T};
}
function drawPdfBoxes(){
  const ov = $('#pdfOverlay'); if(!ov) return; const d = curDoc(), k = S.k || 1;
  const rg = (d.regions||[]).filter(r=>r.page===S.page).map(r=>`<div class="fx region" style="left:${r.x0*k-3}px;top:${r.top*k-3}px;width:${(r.x1-r.x0)*k+6}px;height:${(r.bottom-r.top)*k+6}px"></div>`).join('');
  ov.innerHTML = rg + d.pdf_fields.filter(p=>p.page===S.page && p.bbox).map(p=>{ const [x0,y0,x1,y1] = p.bbox;
    return `<div class="fx" data-pdf-key="${esc(p.id)}" style="left:${x0*k-2}px;top:${y0*k-2}px;width:${(x1-x0)*k+4}px;height:${(y1-y0)*k+4}px"></div>`; }).join('');
  ov.querySelectorAll('.fx[data-pdf-key]').forEach(el=>{
    el.onmouseenter = () => hoverPdf(el.dataset.pdfKey, el); el.onmouseleave = clearHover;
    el.onpointerdown = e => startDrag(e, el.dataset.pdfKey, el);
  });
  paintPdf();
}
function paintPdf(){
  const d = curDoc(); if(!d) return;
  const by = {}; d.fields.forEach(f=>{ const s = vOf(d,f.key).src; if(s) (by[s] = by[s] || []).push(f.key); });
  $$('#pdfOverlay .fx[data-pdf-key]').forEach(el=>{
    const id = el.dataset.pdfKey, pf = pdfFieldOf(d,id), ks = by[id] || [];
    let st = 'none';
    if(ks.length){ const sts = ks.map(fieldState); const allConf = ks.every(k=>vOf(d,k).confirmed);
      st = sts.includes('error')||sts.includes('failed') ? 'error' : sts.includes('warn')||sts.includes('missing') ? 'warn' : allConf ? 'conf' : sts.includes('edited') ? 'edited' : 'ok'; }
    else if(pf && pf.extra) st = 'extra'; else if(pf && pf.blank) st = 'blank';
    el.className = 'fx m-'+st + (S.hover && S.hover.pdf===id ? ' hot' : '') + (S.pick && S.pick.pk===id ? ' picked' : '');
    el.title = pf ? `${pf.label}: ${pf.blank?'blank on the form':dispVal(pf.type,pf.value)} — ${ks.length?'→ '+ks.map(k=>fieldOf(d,k).label).join(', '):'not used yet · drag onto a Drake field'}` : '';
  });
}

/* ---------------- hover link PDF ⇄ Drake ---------------- */
const ST_TXT = {ok:'✓ from PDF', edited:'✎ edited', missing:'missing', warn:'! check', error:'✕ invalid', sent:'✓ in Drake', failed:'✕ Drake rejected', none:'—'};
function labelFor(k, pk){
  const d = curDoc(), f = k && fieldOf(d,k), pf = pk && pdfFieldOf(d,pk), st = k ? fieldState(k) : 'none', issue = k && (statusOf(d.id).issues||{})[k], v = k && vOf(d,k);
  return `<div class="h">${f ? esc(fLabel(f)) : esc(pf?pf.label:'')} <span class="st ${st}">${ST_TXT[st]||st}</span>${v && v.confirmed?' <span class="st conf">confirmed</span>':''}</div>
    ${pf ? `<div class="row"><span class="k">PDF p.${pf.page}</span>${esc(pf.label)}: <span class="v">${pf.blank?'(blank)':esc(dispVal(pf.type,pf.value))}</span></div>` : '<div class="row"><span class="k">PDF</span>not on this form</div>'}
    ${f ? `<div class="row"><span class="k">Drake</span><span class="v">${esc(dispVal(f.type, v.value))}</span></div>` : '<div class="row"><span class="k">Drake</span>not mapped to a Drake field — drag it onto one</div>'}
    ${issue ? `<div class="row" style="color:${issue.level==='error'?'#fca5a5':'#fcd34d'}">${esc(issue.msg)}</div>` : ''}`;
}
function placeLabel(lab, rect){ lab.style.display='block'; const lw=lab.offsetWidth, lh=lab.offsetHeight;
  let x=Math.min(Math.max(8,rect.left), innerWidth-lw-8), y=rect.top-lh-10; if(y<50) y=rect.bottom+10; lab.style.left=x+'px'; lab.style.top=y+'px'; }
function reveal(sc, el){ if(!sc||!el) return; const s=sc.getBoundingClientRect(), r=el.getBoundingClientRect();
  const dy = (r.top<s.top+20||r.bottom>s.bottom-10) ? r.top - s.top - s.height/2 + r.height/2 : 0;
  const dx = (r.left<s.left||r.right>s.right) ? r.left - s.left - s.width/2 + r.width/2 : 0;
  if(dx||dy) sc.scrollBy({top:dy, left:dx, behavior:'smooth'}); }
function markHot(){ $$('.hot').forEach(e=>{ if(!e.closest('#mapScroll')) e.classList.remove('hot'); }); if(!S.hover) return;
  if(S.hover.pdf) $$(`#pdfOverlay [data-pdf-key="${CSS.escape(S.hover.pdf)}"]`).forEach(e=>e.classList.add('hot'));
  (S.hover.form||[]).forEach(k=>{ const w=wrapOf(k); if(w) w.classList.add('hot'); }); }
function hoverPdf(pk, el){
  if(document.body.classList.contains('mapping')) return;
  const d = curDoc(), ks = d.fields.filter(f=>vOf(d,f.key).src===pk).map(f=>f.key); S.hover = {pdf:pk, form:ks}; markHot();
  $('#labA').innerHTML = labelFor(ks[0], pk); placeLabel($('#labA'), el.getBoundingClientRect());
  const tgt = ks.length && S.tab==='screen' && wrapOf(ks[0]);
  if(tgt){ clearTimeout(S.revT); S.revT=setTimeout(()=>reveal($('#formScroll'), tgt),180); $('#labB').innerHTML = labelFor(ks[0], pk); placeLabel($('#labB'), tgt.getBoundingClientRect()); }
  else $('#labB').style.display='none';
}
async function hoverForm(k, w, focus){
  if(document.body.classList.contains('mapping')) return;
  const d = curDoc(), pk = vOf(d,k).src, pf = pk && pdfFieldOf(d,pk);
  if(focus && pf && pf.page && pf.page!==S.page) await renderPage(pf.page);
  S.hover = {pdf: pf && pf.page===S.page ? pk : null, form:[k]}; markHot();
  $('#labB').innerHTML = labelFor(k, pk); placeLabel($('#labB'), w.getBoundingClientRect());
  const pb = pk && $(`#pdfOverlay [data-pdf-key="${CSS.escape(pk)}"]`);
  if(pb){ clearTimeout(S.revT); S.revT=setTimeout(()=>reveal($('#pdfScroll'), pb),180); $('#labA').innerHTML = labelFor(k, pk); placeLabel($('#labA'), pb.getBoundingClientRect()); }
  else $('#labA').style.display='none';
}
function clearHover(){ clearTimeout(S.revT); S.hover=null; markHot(); $('#labA').style.display='none'; $('#labB').style.display='none'; }
function repositionLabels(){ if(!S.hover) return;
  const pb = S.hover.pdf && $(`#pdfOverlay [data-pdf-key="${CSS.escape(S.hover.pdf)}"]`), fb = S.hover.form && S.hover.form[0] && wrapOf(S.hover.form[0]);
  if(pb && $('#labA').style.display==='block') placeLabel($('#labA'), pb.getBoundingClientRect());
  if(fb && $('#labB').style.display==='block') placeLabel($('#labB'), fb.getBoundingClientRect()); }

/* ---------------- live Drake + link Drake fields ---------------- */
function startLive(){ const img = $('#liveImg'); if(S.drake && S.drake.unavailable){ $('#liveWrap').innerHTML = `<div class="excl-note"><b>Live Drake picture is not available.</b><br>${esc(S.drake.error||'')}</div>`; return; }
  if(!img){ $('#liveWrap').innerHTML = '<img id="liveImg" alt="">'; }
  $('#liveImg').onerror = () => { $('#liveWrap').innerHTML = '<div class="excl-note"><b>The live Drake picture stopped.</b><br>Is Drake running on this computer?</div>'; };
  $('#liveImg').src = '/api/drake-view/stream?t='+Date.now(); }
function stopLive(){ const img = $('#liveImg'); if(img){ img.onerror=null; img.removeAttribute('src'); } }
async function linkDrakeFields(){
  const d = curDoc();
  modal('Link Drake fields', `Screen ${d.screen}`, '<div style="padding:30px;text-align:center;color:var(--ink2)"><span class="spinner dk"></span>&nbsp; Opening Drake screen '+esc(d.screen)+' and reading every field…</div>');
  const r = await api('/api/review/discover', {method:'POST', body:JSON.stringify({screen:d.screen, open_screen:true})});
  if(!r.success){ $('#mBody').innerHTML = `<div class="alert bad">${esc(r.error||'Could not read Drake.')}</div><p>${r.unavailable?'This only works on the Windows PC where Drake Tax is installed.':'Open the client\'s return in Drake (Data Entry), then try again.'}</p>`;
    $('#mFoot').innerHTML = '<button class="btn" style="margin-left:auto" onclick="closeModal()">Close</button>'; return; }
  const sug = Object.fromEntries((r.suggestions||[]).map(s=>[s.key,s])), ctl = r.controls || [];
  const fields = d.fields.filter(f=>f.key!=='form_variant');
  const opt = (sel) => `<option value="">— not linked —</option>` + ctl.map(c=>`<option value="${esc(c.aid)}" ${c.aid===sel?'selected':''}>${esc(c.aid)} · ${esc(c.label||'(no label)')} · ${esc(c.control)}</option>`).join('');
  $('#mBody').innerHTML = `<div class="alert info">Drake shows <b>${ctl.length}</b> inputs on screen ${esc(d.screen)}. Suggested links are pre-selected from the labels Drake prints next to each input — check them, then save. Only linked fields are typed into Drake.</div>
    <table class="t"><thead><tr><th>Field on this form</th><th>Now</th><th>Drake input</th></tr></thead><tbody>${fields.map(f=>{ const lk = linkOf(d,f.key), s = sug[f.key];
      return `<tr><td><b>${esc(fLabel(f))}</b></td><td>${lk.aid?`<span class="tag ${lk.how==='linked'?'info':'grey'}">${esc(lk.aid)}</span>`:'<span class="muted">—</span>'}</td>
      <td><select data-lk="${f.key}" style="max-width:380px">${opt(lk.how==='linked' ? lk.aid : (s ? s.aid : (lk.aid||'')))}</select>${s && !lk.aid?` <span class="tag ok">suggested ${Math.round(s.score*100)}%</span>`:''}</td></tr>`; }).join('')}</tbody></table>`;
  $('#mFoot').innerHTML = `<span class="muted" style="font-size:12px">Links are saved per Drake screen and reused for every client.</span><div style="margin-left:auto;display:flex;gap:8px"><button class="btn" onclick="closeModal()">Cancel</button><button class="btn primary" id="saveLinks">Save links</button></div>`;
  $('#saveLinks').onclick = async () => {
    const links = {}; $$('#mBody [data-lk]').forEach(s=>{ const f = fieldOf(d, s.dataset.lk), c = ctl.find(x=>x.aid===s.value);
      if(c && !(f.aid===c.aid && !linkOf(d,f.key).how)) links[f.key] = {aid:c.aid, control:c.control, label:c.label||''}; });
    const sv = await api(`/api/review/links/${encodeURIComponent(d.screen)}`, {method:'POST', body:JSON.stringify({links})});
    if(!sv.success) return toast(sv.error||'Could not save', 5000);
    closeModal(); await loadSession(); renderBody(); toast(`Saved ${Object.keys(links).length} link(s) for screen ${d.screen}.`, 4000);
  };
}

/* ============================================================ 4. summary */
async function viewSummary(){
  S.view='summary'; await flushSave(); renderSteps();
  $('#app').innerHTML = `<div class="page"><div class="card"><span class="spinner dk"></span> Preparing the final review…</div></div>`;
  const r = await api(`/api/review/${S.sid}/summary`); if(!r.success){ $('#app').innerHTML = `<div class="page"><div class="card"><div class="alert bad">${esc(r.error)}</div></div></div>`; return; }
  const rows = Object.fromEntries(r.documents.map(x=>[x.id,x])), planBy = Object.fromEntries(r.plan.map(p=>[p.doc_id,p]));
  const total = r.documents.length, rev = r.documents.filter(x=>x.reviewed).length, exc = r.documents.filter(x=>x.excluded).length;
  const linkedN = p => p ? p.values.filter(v=>!v.ref && linkOf(docById(p.doc_id), v.key).aid).length : 0;
  const inputN = p => p ? p.values.filter(v=>!v.ref).length : 0;
  $('#app').innerHTML = `<div class="page"><div class="card"><h2>Final review</h2>
    <div class="muted">Only reviewed forms and their confirmed values are sent to Drake. Excluded forms are never sent.</div>
    <div class="stats"><div class="stat"><div class="k">Forms</div><div class="v">${total}</div></div><div class="stat"><div class="k">Reviewed</div><div class="v" style="color:#15803d">${rev}</div></div>
      <div class="stat"><div class="k">Excluded</div><div class="v">${exc}</div></div><div class="stat"><div class="k">Still to review</div><div class="v" style="color:${r.blocking.length?'#b45309':'#15803d'}">${r.blocking.length}</div></div>
      <div class="stat"><div class="k">Values to send</div><div class="v">${r.plan.reduce((a,p)=>a+p.values.length,0)}</div></div></div>
    ${r.ready ? '<div class="alert ok">Every form is reviewed or excluded. Continue to the transfer.</div>' : `<div class="alert warn">${r.blocking.length} form(s) still need review: ${r.blocking.map(id=>{ const d = docById(id); return `<a href="#/s/${S.sid}/m/${encodeURIComponent(d.module)}/${encodeURIComponent(id)}">${esc(d.type)} p.${d.page}</a>`; }).join(', ')}.</div>`}
    <div style="display:flex;gap:10px"><button class="btn primary lg" id="toTr" ${r.ready?'':'disabled'}>Continue to transfer →</button></div></div>
    <div class="card">${A().modules.map(m=>{ const p = moduleProgress(m);
      return `<div class="mod-h"><h3>${esc(m.name)}</h3><div class="bar2"><i style="width:${p.n?Math.round(p.done/p.n*100):0}%"></i></div><span class="muted">${p.done}/${p.n} done</span></div>
      <table class="t"><thead><tr><th>Screen</th><th>Form</th><th>Payer</th><th>Status</th><th>Confirmed</th><th>To Drake</th><th></th></tr></thead><tbody>${m.docs.map(id=>{ const x = rows[id], d = docById(id), p = planBy[id];
        const tag = x.excluded ? '<span class="tag grey">excluded</span>' : x.reviewed ? '<span class="tag ok">✓ reviewed</span>' : x.errors ? `<span class="tag bad">${x.errors} to fix</span>` : '<span class="tag warn">not reviewed</span>';
        return `<tr class="click" data-doc="${esc(id)}"><td><b>${esc(d.screen||'—')}</b> ${d.records>1?`<span class="muted">${d.record}/${d.records}</span>`:''}</td><td>${esc(d.type)}</td><td>${esc(d.payer||'')}</td><td>${tag} ${x.warnings&&!x.excluded?`<span class="tag warn">${x.warnings} warning(s)</span>`:''}</td>
          <td>${x.confirmed}/${x.to_confirm}</td><td>${x.excluded?'—':p?(d.zero_value?'nothing to enter (all 0.00)':`${linkedN(p)} of ${inputN(p)} input(s) linked${p.lots?` · ${p.lots.length} lots (8949 import)`:''}`):'<span class="muted">after review</span>'}</td><td><span class="btn">Open</span></td></tr>`; }).join('')}</tbody></table>`; }).join('')}</div></div>`;
  $$('[data-doc]').forEach(tr=>tr.onclick=()=>goDoc(tr.dataset.doc));
  $('#toTr').onclick = () => go(`#/s/${S.sid}/transfer`);
}

/* ============================================================ 5. transfer */
async function viewTransfer(){
  S.view='transfer'; await flushSave(); renderSteps();
  const r = await api(`/api/review/${S.sid}/summary`);
  const tr = S.sess.transfer;
  $('#app').innerHTML = `<div class="page"><div class="card"><h2>Transfer to Drake Tax</h2>
    <div class="muted">Opens the return for the taxpayer SSN on Screen 1, then enters every confirmed value on its Drake screen and record, and reads each one back.
      Values that have no linked Drake field are listed in the report — nothing is skipped silently.</div>
    ${r.success && !r.ready ? `<div class="alert warn" style="margin-top:12px">${r.blocking.length} form(s) are not reviewed yet — only a dry run is possible. <a href="#/s/${S.sid}/summary">Back to the final review</a></div>` : ''}
    <div style="display:flex;gap:10px;align-items:center;margin-top:14px;flex-wrap:wrap">
      <button class="btn lg" id="dryBtn">Dry run (no Drake)</button>
      <button class="btn primary lg" id="goBtn" ${r.success && r.ready ? '' : 'disabled'}>Transfer confirmed values to Drake</button>
      <label style="display:flex;gap:6px;align-items:center;color:var(--ink2)"><input type="checkbox" id="ovw"> Overwrite Drake records that already have values</label>
      <span class="muted" id="drk"></span></div></div>
    <div class="card" id="trCard" ${tr?'':'hidden'}><h3 id="trTitle"></h3><div id="trBody"></div></div></div>`;
  $('#drk').textContent = S.drake ? (S.drake.running ? 'Drake: '+(S.drake.title||'running') : S.drake.unavailable ? 'Drake is not available on this computer' : 'Drake is not running') : '';
  const start = async dry => {
    if(!dry && !confirm('Enter all confirmed values into Drake now? Drake will be driven automatically — do not use the keyboard or mouse until it finishes.')) return;
    const x = await api(`/api/review/${S.sid}/transfer`, {method:'POST', body:JSON.stringify({dry_run:dry, overwrite:$('#ovw').checked})});
    if(!x.success) return toast(x.error || 'Could not start', 6000);
    $('#trCard').hidden = false; pollTransfer();
  };
  $('#dryBtn').onclick = () => start(true); $('#goBtn').onclick = () => start(false);
  if(tr) renderTransfer(tr); if(tr && tr.running) pollTransfer();
}
async function pollTransfer(){
  clearTimeout(S.trT);
  const t = await api(`/api/review/${S.sid}/transfer`); if(!t.success) return;
  S.sess.transfer = t; if(S.view!=='transfer') return; renderTransfer(t);
  if(t.running) S.trT = setTimeout(pollTransfer, 700); else renderSteps();
}
function renderTransfer(t){
  const STC = {verified:'ok', would_enter:'info', mismatch:'warn', failed:'bad', not_linked:'warn', blocked:'warn', reference:'grey'};
  const STL = {verified:'✓ entered & verified', would_enter:'would enter', mismatch:'mismatch', failed:'failed', not_linked:'not linked', blocked:'blocked', reference:'reference only'};
  const cnt = s => (t.results||[]).filter(r=>r.status===s).length;
  if(!$('#trCard')) return; $('#trCard').hidden = false;
  $('#trTitle').innerHTML = t.running ? `<span class="spinner dk"></span> ${t.dry_run?'Dry run':'Transfer'} in progress…` : `${t.dry_run?'Dry run':'Transfer'} finished ${t.error?'<span class="tag bad">stopped</span>':''}`;
  const byDoc = {}; (t.results||[]).forEach(r=>(byDoc[r.doc_id] = byDoc[r.doc_id] || []).push(r));
  const docMsg = Object.fromEntries((t.docs||[]).map(x=>[x.doc_id,x]));
  const ids = [...new Set([...(t.docs||[]).map(x=>x.doc_id), ...Object.keys(byDoc)])];
  $('#trBody').innerHTML = (t.error?`<div class="alert bad">${esc(t.error)}</div>`:'') +
    `<div class="stats">${['verified','would_enter','mismatch','failed','not_linked','blocked','reference'].filter(s=>cnt(s)).map(s=>`<div class="stat"><div class="k">${STL[s]}</div><div class="v">${cnt(s)}</div></div>`).join('')}</div>` +
    ids.map(id=>{ const d = docById(id); if(!d) return ''; const m = docMsg[id];
      return `<div class="mod-h"><h3>${esc(d.screen||'—')} · ${esc(d.type)} — ${esc(d.payer||'')}</h3>${m?`<span class="tag ${m.status==='entered'||m.status==='import_file'?'ok':m.status==='dry_run'?'info':m.status==='nothing'?'grey':'warn'}">${esc(m.message)}</span>`:''}</div>
      ${(byDoc[id]||[]).length?`<table class="t"><thead><tr><th>Field</th><th>Value</th><th>Result</th><th>Details</th></tr></thead><tbody>${byDoc[id].map(r=>`<tr><td>${esc(r.label)}</td><td class="v">${esc(r.value)}</td><td><span class="tag ${STC[r.status]||'grey'}">${STL[r.status]||esc(r.status)}</span></td><td class="muted">${esc(r.message)}</td></tr>`).join('')}</tbody></table>`:''}`; }).join('') +
    `<div class="logs">${(t.log||[]).map(esc).join('\n')}</div>`;
}

/* ============================================================ Drake status + boot */
async function checkDrake(){
  clearTimeout(S.drakeT); const r = await api('/api/drake-view/status');
  if(r.unavailable){ S.drake = {unavailable:true, error:r.error}; setDot('warn','Drake not available on this computer'); return; }
  if(!r.success){ S.drake = null; setDot('warn', r.offline ? 'App server not reachable' : (r.error||'Drake status unknown')); S.drakeT = setTimeout(checkDrake, 10000); return; }
  S.drake = r; setDot(r.running?'on':'warn', r.running ? (r.title||'Drake Tax 2025') : 'Drake Tax 2025 is not running');
  S.drakeT = setTimeout(checkDrake, document.hidden ? 15000 : 6000);
}
function setDot(c,t){ $('#ldot').className='ldot '+c; $('#ltxt').textContent=t; $('#ltxt').title=t; }
(async function boot(){
  S.fit = store.get('fit','form');
  const c = await api('/api/review/catalog'); S.catalog = c.success ? c : {forms:{}, modules:[]};
  if(!location.hash) location.hash = '#/upload';
  route(); checkDrake();
})();
