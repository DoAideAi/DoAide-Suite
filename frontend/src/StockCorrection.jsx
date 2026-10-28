import React,{useEffect,useState} from 'react';
import {api,post} from './client';

export function StockCorrection({record,workflow,onSaved}){
  const [stock,setStock]=useState([]),[sku,setSku]=useState(''),[error,setError]=useState(''),[busy,setBusy]=useState(false),[message,setMessage]=useState('');
  const load=()=>Promise.all([api('/inventory'),api('/integrations')]).then(([rows,connections])=>setStock(rows.filter(s=>!s.data?._inventory&&!(connections.authorities?.inventory_lots?.active&&/^(lot:|finished:)/.test(s.sku))))).catch(e=>setError(e.message));
  useEffect(()=>{load();},[record.id]);
  const selected=stock.find(s=>s.sku===sku);
  async function submit(e){e.preventDefault();setBusy(true);setError('');setMessage('');const form=e.currentTarget,f=new FormData(form);try{
    await post('/inventory/adjustments',{record_id:record.id,sku,expected_quantity:selected.quantity,expected_held:selected.held,delta:f.get('delta'),reference:f.get('reference'),reason:f.get('reason'),file_id:f.get('file')});
    setMessage('Count correction recorded. Original production and dispatch documents are preserved.');form.reset();setSku('');await load();await onSaved();
  }catch(e){setError(e.message);}finally{setBusy(false);}}
  return <details className="resource-card"><summary>Correct a physical stock count</summary><p>Use a signed quantity change and count evidence. Reserved stock stays protected and quarantined stock stays on hold. For connected Batch lots, use the Inventory lot correction action.</p>{error&&<p className="error" role="alert">{error}</p>}{message&&<p role="status">{message}</p>}
    <form className="operation-form" onSubmit={submit}><label>SKU / lot<select value={sku} onChange={e=>setSku(e.target.value)} required><option value="">Choose stock…</option>{stock.map(s=><option key={s.sku} value={s.sku}>{s.sku} · {s.name}</option>)}</select></label>{selected&&<p>Reviewed count: {selected.quantity} {selected.unit} · held: {selected.held}</p>}
    <label>Quantity change<input name="delta" type="number" min="-1000000000" max="1000000000" step="any" required placeholder="e.g. -2 or 3"/></label><label>Unique correction reference<input name="reference" maxLength="120" required/></label><label>Reason<textarea name="reason" minLength="5" maxLength="2000" required/></label><label>Uploaded count evidence<select name="file" required><option value="">Choose evidence…</option>{workflow.files.filter(f=>!f.deleted_at).map(f=><option value={f.id} key={f.id}>{f.name}</option>)}</select></label><button className="button primary small" disabled={busy||!selected}>Approve count correction</button><button type="button" className="button secondary small" onClick={load}>Refresh reviewed stock</button></form>
  </details>;
}
