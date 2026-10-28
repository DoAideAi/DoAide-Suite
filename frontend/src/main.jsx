import React, { useEffect, useState } from 'react';
import { createRoot } from 'react-dom/client';
import { ArrowUpRight, ArrowLeft, ArrowRight, Check, CheckCircle2, ChevronRight, Circle, ClipboardList, Download, FileText, Grid2X2, Layers3, LogOut, Plus, RefreshCw, Search, ShieldCheck, Sparkles, Trash2, X } from 'lucide-react';
import './styles.css';

import { api } from './client';
import { AccountLink } from './AuthRecovery';
import { Operations, WorkspaceTools, Portal, ContractorPortal } from './Operations';

const initials = { scope: 'Sc', collect: 'Co', amc: 'Am', rfq: 'Rq', tender: 'Te', handover: 'Ha', orderdesk: 'Or', batch: 'Ba', fees: 'Fe', renew: 'Re', sop: 'So', claimpack: 'Cl' };
const groups = ['All products', 'Revenue', 'Operations', 'People'];
function blank(fields) { return Object.fromEntries(fields.map(f => [f.key, f.type === 'rows' ? [] : f.type === 'select' ? f.options[0] : ''])); }

function Auth({ onLogin }) {
  const [register, setRegister] = useState(true);
  const [authMessage,setAuthMessage]=useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  async function submit(event) {
    event.preventDefault(); setBusy(true); setError('');
    try { const result=await api(`/auth/${register ? 'register' : 'login'}`, { method: 'POST', body: JSON.stringify({ email, password }) });if(result.verification_required){setAuthMessage(result.message);setRegister(false);}else onLogin(result); }
    catch (e) { setError(e.message); } finally { setBusy(false); }
  }
  async function requestLink(purpose){setBusy(true);setError('');setAuthMessage('');try{const r=await api('/auth/request-'+purpose,{method:'POST',body:JSON.stringify({email})});setAuthMessage(r.message);}catch(e){setError(e.message);}finally{setBusy(false);}}
  return <div className="auth-layout">
    <section className="auth-story"><a className="brand" href="#"><span className="brand-icon">d<span>.</span></span>doaide<span className="brand-dot">.</span></a>
      <div className="auth-copy"><span className="eyebrow">A LITTLE LESS ADMIN. A LOT MORE DONE.</span><h1>Make room for<br/>the work<br/><span>that matters.</span></h1><p>Twelve focused tools for the details that keep your business moving.</p>
        <div className="auth-chips"><span>Collect what’s owed</span><span>Keep work on track</span><span>Give your team clarity</span></div></div>
      <div className="auth-footer"><Layers3 size={18}/> One workspace. Twelve ways forward.</div>
    </section>
    <section className="auth-form-area"><form className="auth-form" onSubmit={submit}><span className="pill"><span className="live-dot"/> Local development preview</span><h2>{register ? 'Your next chapter starts here.' : 'Welcome back.'}</h2><p>{register ? 'Create a local account to manage your products and save your work.' : 'Sign in to your local DoAide workspace.'}</p>
      <label>Email address<input type="email" autoComplete="email" required value={email} onChange={e => setEmail(e.target.value)} placeholder="you@company.com"/></label>
      <label>Password<input type="password" autoComplete={register ? 'new-password' : 'current-password'} minLength={12} maxLength={256} required value={password} onChange={e => setPassword(e.target.value)} placeholder="At least 12 characters"/></label>
      {error && <div className="error" role="alert">{error}</div>}{authMessage&&<div className="notice success" role="status">{authMessage}</div>}
      <button className="button primary wide" disabled={busy}>{busy ? 'Opening workspace…' : register ? 'Create local workspace' : 'Sign in'}<ArrowRight size={17}/></button>
      <button type="button" className="text-button wide" onClick={() => {setRegister(!register); setError('');}}>{register ? 'Already have a local account? Sign in' : 'Create a new local account'}</button>
      <div className="inline-actions"><button type="button" className="text-button" disabled={busy||!email} onClick={()=>requestLink('reset')}>Forgot password?</button><button type="button" className="text-button" disabled={busy||!email} onClick={()=>requestLink('verification')}>Resend verification</button></div><div className="auth-note"><ShieldCheck size={18}/><span>Saved on this computer. Use Workspace tools to invite your team. Verification and recovery links use your configured email service.</span></div>
    </form></section>
  </div>;
}

function Input({ field, value, onChange, prefix = '', disabled = false }) {
  const id = prefix + field.key;
  if (field.type === 'rows') return <fieldset className="rows-field" disabled={disabled}><legend>{field.label}</legend>
    <div className="repeat-rows">{(value || []).map((row, i) => <div className="repeat-row" key={i}>
      <div className="row-number">{String(i + 1).padStart(2, '0')}</div><div className="row-fields">{field.columns.map(column => <Input key={column.key} field={column} value={row[column.key] ?? ''} prefix={`${id}-${i}-`} onChange={next => onChange(value.map((r, j) => j === i ? { ...r, [column.key]: next } : r))}/>)}</div>
      <button type="button" className="icon-button remove-row" aria-label={`Remove ${field.label} row ${i + 1}`} onClick={() => onChange(value.filter((_, j) => i !== j))}><Trash2 size={15}/></button>
    </div>)}</div><button type="button" className="button small secondary" onClick={() => onChange([...(value || []), blank(field.columns)])}><Plus size={15}/>Add row</button>
  </fieldset>;
  const props = { id, value: value ?? '', disabled, required: field.required, onChange: e => onChange(e.target.value) };
  return <label className={field.type === 'textarea' ? 'full-field' : ''} htmlFor={id}>{field.label}{!field.required && <span className="optional">Optional</span>}
    {field.type === 'textarea' ? <textarea {...props} rows={4}/> : field.type === 'select' ? <select {...props}>{field.options.map(v => <option key={v}>{v}</option>)}</select> : <input {...props} type={field.type} min={field.min} max={field.max} step={field.integer ? '1' : 'any'}/>}
  </label>;
}

function Result({ result, record, onStatus, busy, dirty }) {
  if (!result) return <aside className="result-panel empty-result"><div className="result-symbol"><ClipboardList size={30}/></div><h3>A clear next step starts here.</h3><p>Enter your details, or load an example, then preview the result.</p><div className="result-steps"><span><CheckCircle2 size={16}/>Reviewable calculations</span><span><CheckCircle2 size={16}/>Checks before completion</span><span><CheckCircle2 size={16}/>Save and export your work</span></div></aside>;
  const columns = [...new Set(result.items.flatMap(row => Object.keys(row)))];
  return <aside className="result-panel"><div className="section-label"><span>INTAKE PREVIEW</span><span>{result.as_of}</span></div><h2>{result.heading}</h2>{record&&<p className="result-note">This preview uses the saved intake. Operations shows the current ledger, approvals and completion status.</p>}
    <div className="result-metrics">{Object.entries(result.metrics).map(([label, value]) => <div key={label}><span>{label}</span><strong>{value}</strong></div>)}</div>
    {result.blockers.length > 0 && <div className="check-box"><h4>Before marking reviewed</h4><ul>{result.blockers.map((b, i) => <li key={i}>{b}</li>)}</ul></div>}
    {result.items.length > 0 && <div className="table-scroll"><table><thead><tr>{columns.map(c => <th key={c}>{c}</th>)}</tr></thead><tbody>{result.items.map((item, i) => <tr key={i}>{columns.map(c => <td key={c}>{String(item[c] ?? '')}</td>)}</tr>)}</tbody></table></div>}
    {result.narrative && <p className="narrative">{result.narrative}</p>}
    {result.warnings.map((warning, i) => <p className="result-note" key={i}>{warning}</p>)}
    {record && !dirty && <div className="result-actions"><a className="button secondary small" href={`/api/records/${record.id}/export`} download><Download size={15}/>Export JSON</a><button type="button" className="button secondary small" onClick={() => window.print()}><FileText size={15}/>Print result</button>{record.status === 'draft' && <button className="button primary small" type="button" onClick={() => onStatus('reviewed')} disabled={busy || !result.can_review}><Check size={15}/>Mark reviewed</button>}</div>}
  </aside>;
}

function ScopeDoc({ slug }) {
  const [text, setText] = useState('Loading product scope…');
  useEffect(() => { let active = true; api(`/products/${slug}/scope`).then(d => active && setText(d.markdown)).catch(e => active && setText(e.message)); return () => {active = false;}; }, [slug]);
  return <article className="scope-doc">{text.split('\n').map((line, i) => line.startsWith('# ') ? <h1 key={i}>{line.slice(2)}</h1> : line.startsWith('## ') ? <h2 key={i}>{line.slice(3)}</h2> : line.startsWith('### ') ? <h3 key={i}>{line.slice(4)}</h3> : <p key={i}>{line || '\u00a0'}</p>)}</article>;
}

function Workspace({ user, logout }) {
  const [products, setProducts] = useState([]), [records, setRecords] = useState([]);
  const [moreRecords,setMoreRecords]=useState(false);
  const [selected, setSelected] = useState(null), [category, setCategory] = useState('All products'), [search, setSearch] = useState('');
  const [tab, setTab] = useState('Intake'), [payload, setPayload] = useState({}), [title, setTitle] = useState('');
  const [record, setRecord] = useState(null), [result, setResult] = useState(null), [audit, setAudit] = useState([]);
  const [busy, setBusy] = useState(false), [error, setError] = useState(''), [message, setMessage] = useState(''), [dirty, setDirty] = useState(false);
  const [mobileNav, setMobileNav] = useState(false);
  const [toolsOpen, setToolsOpen] = useState(!!new URLSearchParams(location.search).get('invite'));
  async function refresh() { const next=await api('/records');setRecords(next);setMoreRecords(next.length===500); }
  async function loadMore(){try{const next=await api('/records?offset='+records.length);setRecords(r=>[...r,...next]);setMoreRecords(next.length===500);}catch(e){setError(e.message);}}
  useEffect(() => { Promise.all([api('/products'), api('/records')]).then(([p, r]) => {setProducts(p); setRecords(r); setMoreRecords(r.length===500);}).catch(e => setError(e.message)); }, []);
  useEffect(() => { const listener = e => {if (dirty) {e.preventDefault(); e.returnValue = '';}}; window.addEventListener('beforeunload', listener); return () => window.removeEventListener('beforeunload', listener); }, [dirty]);
  function canLeave() { return !busy && (!dirty || window.confirm('Discard the changes that have not been saved?')); }
  function selectProduct(p) {
    if (!canLeave()) return;
    setSelected(p); setPayload(p ? blank(p.fields) : {}); setTitle(''); setRecord(null); setResult(null); setDirty(false); setError(''); setMessage(''); setAudit([]); setTab('Intake'); setMobileNav(false); window.scrollTo(0, 0);
  }
  function change(key, value) {setPayload(p => ({...p, [key]: value})); setDirty(true); setResult(null); setMessage('');}
  function example() {
    if (!canLeave()) return;
    setPayload(structuredClone(selected.sample)); setTitle(`Example · ${selected.name}`); setRecord(null); setResult(null); setDirty(true); setAudit([]); setMessage('Synthetic example loaded. Save to keep a copy in your workspace.'); setError('');
  }
  async function run(save) {
    setBusy(true); setError(''); setMessage('');
    try {
      if (save) {
        const data = await api(record ? `/records/${record.id}` : `/products/${selected.slug}/records`, {method: record ? 'PUT' : 'POST', body: JSON.stringify({title: title.trim(), payload, version: record?.version})});
        setRecord(data); setPayload(data.payload); setResult(data.result); setDirty(false); setMessage('Saved to your workspace.'); await refresh(); setAudit(await api(`/records/${data.id}/audit`));
      } else setResult(await api(`/products/${selected.slug}/preview`, {method: 'POST', body: JSON.stringify(payload)}));
    } catch (e) {setError(e.message);} finally {setBusy(false);}
  }
  async function openRecord(r) {
    if (!canLeave()) return;
    setBusy(true); setError(''); setMessage('');
    try { const data = await api(`/records/${r.id}`); setSelected(products.find(p=>p.slug===data.product)); setRecord(data); setTitle(data.title); setPayload(data.payload); setResult(data.result); setDirty(false); setTab('Operations'); setAudit(await api(`/records/${r.id}/audit`)); }
    catch (e) {setError(e.message);} finally {setBusy(false);}
  }
  async function status(next) {
    setBusy(true); setError('');
    try { const data = await api(`/records/${record.id}/status`, {method: 'POST', body: JSON.stringify({status: next, version: record.version})}); setRecord(data); setResult(data.result); await refresh(); setAudit(await api(`/records/${record.id}/audit`)); setMessage(`Record ${next === 'draft' ? 'restored to draft' : next}.`); }
    catch (e) {setError(e.message);} finally {setBusy(false);}
  }
  const productRecords = records.filter(r => r.product === selected?.slug);
  const filtered = products.filter(p => (category === 'All products' || p.category === category) && `${p.name} ${p.subtitle} ${p.buyer}`.toLowerCase().includes(search.toLowerCase()));
  return <div className="app-layout">
    <aside className={`sidebar ${mobileNav ? 'mobile-open' : ''}`}><button className="icon-button close-navigation" aria-label="Close product navigation" onClick={() => setMobileNav(false)}><X size={18}/></button><button className="brand" onClick={() => selectProduct(null)}><span className="brand-icon">d<span>.</span></span>doaide<span className="brand-dot">.</span></button>
      <div className="workspace-label"><span className="workspace-avatar">D</span><div>Business workspace<small>Local development</small></div><ChevronRight size={15}/></div>
      <button className={`nav-item ${!selected ? 'active' : ''}`} onClick={() => selectProduct(null)}><Grid2X2 size={18}/>Overview</button>
      <button className="nav-item" onClick={() => {if(canLeave())setToolsOpen(true);}}><ShieldCheck size={18}/>Workspace tools</button><span className="nav-label">YOUR PRODUCTS <span>12</span></span><nav>{products.map(p => <button key={p.slug} className={`nav-item ${selected?.slug === p.slug ? 'active' : ''}`} onClick={() => selectProduct(p)}><span className={`mini-icon ${p.category.toLowerCase()}`}>{initials[p.slug]}</span>{p.name}{records.some(r => r.product === p.slug) && <span className="nav-count">{records.filter(r => r.product === p.slug).length}</span>}</button>)}</nav>
      <div className="sidebar-bottom"><div className="build-note"><span className="live-dot"/>Operations available<small>Local build · v0.2</small></div><button className="account" onClick={() => {if (canLeave()) logout();}}><span className="account-avatar">{user.email[0].toUpperCase()}</span><span>{user.email}<small>Sign out</small></span><LogOut size={16}/></button></div>
    </aside>
    {toolsOpen&&<WorkspaceTools user={user} onClose={()=>setToolsOpen(false)} onRefresh={refresh} onOpenRecord={r=>{setToolsOpen(false);openRecord(r);}}/>}<main className="main-content"><header className="topbar"><button className="icon-button menu-toggle" aria-label="Toggle product navigation" onClick={() => setMobileNav(!mobileNav)}><Layers3 size={20}/></button><span>Workspace <ChevronRight size={13}/> {selected ? selected.name : 'Overview'}</span><span className="topbar-status"><span className="live-dot"/>Local preview</span></header>
      <div className="page-content">
        {!selected ? <><div className="intro"><div><span className="eyebrow">BUILT FOR THE WAY YOU WORK</span><h1>A little more clarity.<br/>A lot more <span>momentum.</span></h1><p>Your business has a lot of moving parts. Give each one a place.</p></div><div className="intro-art" aria-hidden="true"><div className="art-orbit"/><div className="art-card one"><CheckCircle2/>All in one place</div><div className="art-card two"><Layers3/>Made for your next step</div><span className="art-spark">✳</span></div></div>
          <div className="overview-stats"><div><span>Focused products</span><strong>{products.length}<small>ready to explore</small></strong></div><div><span>Your saved work</span><strong>{records.length}<small>across the workspace</small></strong></div><div><span>Reviewed records</span><strong>{records.filter(r => r.status === 'reviewed').length}<small>checked and recorded</small></strong></div><div><span>Your starting point</span><strong className="stat-text">Scope <ArrowUpRight size={18}/></strong><small>Turn extra work into a change request</small></div></div>
          <div className="catalog-heading"><div><h2>Find your next step</h2><p>Start small. Bring a real workflow into focus.</p></div><div className="search"><Search size={17}/><input aria-label="Search products" placeholder="Find a product…" value={search} onChange={e => setSearch(e.target.value)}/></div></div>
          <div className="filters">{groups.map(g => <button className={category === g ? 'selected' : ''} key={g} onClick={() => setCategory(g)}>{g}{g === 'All products' && <span>12</span>}</button>)}</div>
          <div className="product-grid">{filtered.map(p => <button className="product-card" key={p.slug} onClick={() => selectProduct(p)}><div className="card-top"><span className={`product-icon ${p.category.toLowerCase()}`}>{initials[p.slug]}</span><span className="card-category">{p.category}</span></div><h3>{p.name}<ArrowUpRight size={18}/></h3><p>{p.subtitle}</p><div className="card-bottom"><span>{p.buyer}</span><ArrowRight size={16}/></div></button>)}</div>{!filtered.length && <div className="empty-state">No products match this search.</div>}
          <div className="overview-footer"><ShieldCheck size={18}/><p>All twelve products have operational workspaces with roles, evidence files and audit history. Configure delivery providers in Workspace tools.</p></div>
        </> : <><button className="back-link" onClick={() => selectProduct(null)}><ArrowLeft size={15}/>All products</button><div className="product-heading"><div className={`product-icon large ${selected.category.toLowerCase()}`}>{initials[selected.slug]}</div><div><span className="eyebrow">DOAIDE / {selected.category.toUpperCase()}</span><h1>{selected.name}</h1><p>{selected.subtitle}</p></div><span className="pill stage-pill">Operations</span></div>
          <div className="tabs">{['Intake', 'Operations', 'Saved records', 'Product scope'].map(t => <button key={t} className={tab === t ? 'active' : ''} onClick={() => setTab(t)}>{t}{t === 'Saved records' && <span>{productRecords.length}</span>}</button>)}</div>
          {tab === 'Operations' ? <Operations record={record} dirty={dirty} onRecordsChanged={refresh} onOpenRecord={openRecord}/> : tab === 'Product scope' ? <ScopeDoc slug={selected.slug}/> : tab === 'Saved records' ? <div className="saved-panel"><div className="saved-heading"><h2>Your {selected.name.toLowerCase()} records</h2><button className="button secondary small" onClick={() => selectProduct(selected)}><Plus size={16}/>New record</button></div>{!productRecords.length ? <div className="empty-state"><FileText size={28}/><h3>Your first record belongs here.</h3><p>Use the workbench to create and save it.</p></div> : <div className="record-list">{productRecords.map(r => <button className="record-row" key={r.id} onClick={() => openRecord(r)}><FileText size={20}/><span><strong>{r.title}</strong><small>Updated {new Date(r.updated_at).toLocaleString()} · Version {r.version}</small></span><span className={`status ${r.status}`}>{r.status}</span><ChevronRight size={17}/></button>)}</div>}</div> : <>
            <div className="workbench-toolbar"><span>{record ? <><span className={`status ${record.status}`}>{record.status}</span> Version {record.version}{dirty ? ' · Unsaved changes' : ''}</> : 'Start with your details or explore an example.'}</span><div><button className="button secondary small" onClick={example} disabled={busy}>Load example</button><button className="button secondary small" onClick={() => selectProduct(selected)} disabled={busy}><Plus size={15}/>New</button></div></div>
            <div className="workbench"><form className="editor-panel" onSubmit={e => {e.preventDefault(); run(true);}}><div className="section-label"><span>THE DETAILS</span><FileText size={16}/></div><h2>{record ? 'Your working record' : 'Create a working record'}</h2><label>Record title<input required maxLength={160} value={title} disabled={record?.status === 'archived'} onChange={e => {setTitle(e.target.value); setDirty(true); setMessage('');}} placeholder={`e.g. ${selected.name} · October review`}/></label><div className="editor-fields">{selected.fields.map(f => <Input key={f.key} field={f} value={payload[f.key]} disabled={record?.status === 'archived'} onChange={v => change(f.key, v)}/>)}</div><div className="editor-actions">{record?.status === 'archived' ? <button type="button" className="button primary" disabled={busy} onClick={() => status('draft')}><RefreshCw size={16}/>Restore to draft</button> : <><button type="button" className="button secondary" disabled={busy} onClick={() => run(false)}>Preview result</button><button type="submit" className="button primary" disabled={busy}>{busy ? 'Working…' : record ? 'Save changes' : 'Save record'}<ArrowRight size={16}/></button></>}</div><p className="fine-print">Changes invalidate pending approvals. Operational commitments require explicit adjustments.</p>{record && !dirty && <button type="button" className="button secondary" onClick={()=>setTab('Operations')}>Open operations <ArrowRight size={16}/></button>}</form>
              <Result result={result} record={record} onStatus={status} busy={busy} dirty={dirty}/>
            </div>{record && <div className="history-panel"><div><h3>Record history</h3><p>{audit.map(a => `${a.action} · v${a.version} · ${new Date(a.created_at).toLocaleString()}`).join('\n')}</p></div>{record.status !== 'archived' && <button className="text-button" disabled={busy || dirty} onClick={() => status('archived')}>Archive record</button>}</div>}
          </>}
        </>}
        {moreRecords&&<button className="button secondary" onClick={loadMore}>Load more workspace records</button>}{error && <div className="toast error" role="alert"><span>{error}</span><button className="icon-button" aria-label="Dismiss error" onClick={() => setError('')}><X size={17}/></button></div>}
        {message && <div className="toast success" role="status"><CheckCircle2 size={18}/><span>{message}</span><button className="icon-button" aria-label="Dismiss notification" onClick={() => setMessage('')}><X size={17}/></button></div>}
      </div>
    </main>
  </div>;
}

function App() {
  const [user, setUser] = useState(null), [loading, setLoading] = useState(true), [error, setError] = useState('');
  useEffect(() => {api('/auth/me').then(setUser).catch(e => {if (e.status !== 401) setError(e.message);}).finally(() => setLoading(false));}, []);
  async function logout() {try {await api('/auth/logout', {method: 'POST'}); setUser(null);} catch (e) {setError(e.message);}}
  if (loading) return <div className="loading">Opening DoAide…</div>;
  return <>{error && <div className="global-error" role="alert">{error}<button onClick={() => location.reload()}>Retry</button></div>}{user ? <Workspace user={user} logout={logout}/> : <Auth onLogin={setUser}/>}</>;
}

const portalToken=new URLSearchParams(location.search).get('portal');
const taskToken=new URLSearchParams(location.search).get('task');
const authPurpose=new URLSearchParams(location.search).get('auth');
const authToken=new URLSearchParams(location.search).get('token');
createRoot(document.getElementById('root')).render(['verify','reset'].includes(authPurpose)&&authToken?<AccountLink purpose={authPurpose} token={authToken}/>:taskToken?<ContractorPortal token={taskToken}/>:portalToken?<Portal token={portalToken}/>:<App/>);
