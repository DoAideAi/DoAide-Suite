import React, {useEffect, useState} from 'react';
import {api, post} from './client';

const title=s=>s.replaceAll('_',' ').replaceAll('-',' ');
const money=n=>new Intl.NumberFormat('en-IN',{style:'currency',currency:'INR'}).format(n/100);

export function BillingPanel(){
  const [data,setData]=useState(null),[error,setError]=useState(''),[busy,setBusy]=useState(false),[message,setMessage]=useState('');
  const load=()=>api('/billing').then(setData).catch(e=>setError(e.message));
  useEffect(()=>{load();},[]);
  const pending=data?.jobs.some(j=>['queued','running','failed'].includes(j.state));
  useEffect(()=>{if(pending){const id=setInterval(load,5000);return()=>clearInterval(id);}},[pending]);
  async function request(path,body={}){setBusy(true);setError('');try{await post('/billing/'+path,body);setMessage('Request queued. The result will appear below.');await load();}catch(e){setError(e.message);}finally{setBusy(false);}}
  return <section className="resource-card"><div className="resource-title"><h3>Plan & usage</h3><button className="button secondary small" onClick={load}>Refresh</button></div>
    {error&&<p role="alert" className="error">{error}</p>}{message&&<p role="status">{message}</p>}
    {data?<><h4>{data.plan.name}</h4><p>{data.mode==='local'?'Local access is active. Subscription billing is not connected.':'Test billing only · '+title(data.account.status)+'. Checkout returns do not grant access until the provider has been reconciled.'}</p>
      <div className="usage-grid">{Object.entries(data.usage).map(([key,value])=><div key={key}><strong>{title(key)}</strong><span>{value.toLocaleString()} / {data.plan.limits[key]===null?'unlimited':data.plan.limits[key].toLocaleString()}</span>{data.plan.limits[key]>0&&<progress aria-label={title(key)+' usage'} value={value} max={data.plan.limits[key]}/>}</div>)}</div>
      <p>Included products: {data.plan.products.length?data.plan.products.join(', '):'No new products in this plan'}. Existing records and exports remain accessible.</p>
      {data.mode==='stripe-test'&&data.owner&&<><p>{data.configured?'Choose a test plan to prepare a hosted checkout.':'The test billing connection needs configuration before checkout can run.'}</p><div className="plan-options">{Object.entries(data.plans).filter(([,p])=>p.price_id).map(([key,plan])=><div className="entity" key={key}><strong>{plan.name}</strong><small>{plan.products.join(', ')}</small><button disabled={busy||!data.configured} className="button secondary small" onClick={()=>request('checkout',{plan:key})}>Prepare test checkout</button></div>)}</div><div className="inline-actions"><button disabled={busy} className="button secondary small" onClick={()=>request('portal')}>Open test billing portal</button><button disabled={busy} className="button secondary small" onClick={()=>request('sync')}>Reconcile subscription</button></div></>}
      {data.jobs.map(job=><div key={job.id} className="entity"><strong>{title(job.kind)} · {job.state}</strong>{job.last_error&&<p>{job.last_error}</p>}{job.result?.url&&job.state==='delivered'&&(!job.result.expires_at||job.result.expires_at>Date.now()/1000)&&<a className="button primary small" href={job.result.url} target="_blank" rel="noreferrer">Continue to Stripe test {job.kind==='billing-portal'?'portal':'checkout'}</a>}{data.owner&&['blocked','failed','dead-letter'].includes(job.state)&&<button className="button secondary small" onClick={async()=>{try{await post('/jobs/'+job.id+'/retry',{});await load();}catch(e){setError(e.message);}}}>Retry after resolving the issue</button>}</div>)}
    </>:<p>Loading plan…</p>}
  </section>;
}

export function ReportsPanel({onOpenRecord}){
  const [data,setData]=useState(null),[product,setProduct]=useState(''),[error,setError]=useState(''),[attention,setAttention]=useState(false);
  const load=()=>api('/reports/portfolio').then(setData).catch(e=>setError(e.message));
  useEffect(()=>{load();},[]);
  const query=product?'?product='+product:'';
  const records=data?.records.filter(r=>(!product||r.product===product)&&(!attention||r.alerts.length))||[];
  return <section className="resource-card"><div className="resource-title"><h3>Portfolio reports</h3><button className="button secondary small" onClick={load}>Refresh</button></div>{error&&<p className="error" role="alert">{error}</p>}
    {data?<><p>Business date {data.business_date}. {data.basis}</p><div className="inline-form"><label>Product<select value={product} onChange={e=>setProduct(e.target.value)}><option value="">All products</option>{Object.keys(data.totals).map(p=><option key={p} value={p}>{p}</option>)}</select></label><label className="report-toggle"><input type="checkbox" checked={attention} onChange={e=>setAttention(e.target.checked)}/>Needs attention only</label><a className="button secondary small" href={'/api/reports/portfolio.csv'+query} download>Export portfolio CSV</a><a className="button secondary small" href={'/api/reports/accounting.csv'+(['fees','collect'].includes(product)?query:'')} download>Export accounting CSV</a></div>
      <div className="report-cards">{Object.entries(data.totals).filter(([key])=>!product||key===product).map(([key,total])=><div className="entity" key={key}><strong>{key}</strong><p>{total.records} active records · {total.attention} need attention</p>{total.balance_paise!==undefined&&<><span>Outstanding {money(total.balance_paise)}</span><span>Due now {money(total.due_now_paise)}</span><details><summary>Aging</summary>{Object.entries(total.aging_paise).map(([bucket,value])=><p key={bucket}>{title(bucket)}: {money(value)}</p>)}</details></>}{total.annualized_paise!==undefined&&<span>Annualized commitment {money(total.annualized_paise)}</span>}</div>)}</div>
      {data.truncated&&<p role="status">Showing the first 500 records. The CSV export includes all {data.total_records} records.</p>}
      <div className="table-scroll"><table><thead><tr><th>Record</th><th>Product</th><th>Stage</th><th>Attention</th><th>Facts</th></tr></thead><tbody>{records.map(r=><tr key={r.record_id}><td><button className="text-button" onClick={()=>onOpenRecord({id:r.record_id,product:r.product})}>{r.title}</button>{r.deadline&&<small>Deadline: {r.deadline}</small>}</td><td>{r.product}</td><td>{title(r.stage)}</td><td>{r.alerts.join(' · ')||'—'}</td><td><details><summary>View facts</summary><dl>{Object.entries(r.facts).map(([key,v])=><div key={key}><dt>{title(key)}</dt><dd>{key.endsWith('_paise')&&typeof v==='number'?money(v):typeof v==='object'?JSON.stringify(v):String(v??'—')}</dd></div>)}</dl></details></td></tr>)}</tbody></table></div>{!records.length&&<p>No saved records match these filters.</p>}
    </>:<p>Loading portfolio…</p>}
  </section>;
}
