import React, {useState} from 'react';
import {post} from './client';

export function TechnicianLinks({record, workflow, onSaved}) {
  const [link,setLink]=useState(''),[error,setError]=useState(''),[busy,setBusy]=useState(false);
  const visits=workflow.items.filter(i=>i.kind==='visit'&&(!i.data._status||i.data._status==='scheduled'));
  async function submit(event) {
    event.preventDefault();setBusy(true);setError('');setLink('');
    const id=new FormData(event.currentTarget).get('visit');
    const visit=visits.find(i=>i.id===id);
    try {
      const result=await post(`/records/${record.id}/contractor-links`,{item_id:id,recipient:visit.data.technician,hours:72});
      setLink(location.origin+result.path);await onSaved();
    } catch(error) {setError(error.message);} finally {setBusy(false);}
  }
  return <details className="contractor-share"><summary>Share one service visit with its technician</summary>
    <p>This link exposes only the assigned asset, visit and checklist.</p>
    <form className="operation-form" onSubmit={submit}>
      <label>Scheduled visit<select name="visit" required><option value="">Select…</option>{visits.map(i=><option key={i.id} value={i.id}>{i.data.start} · {i.data.technician}</option>)}</select></label>
      <button className="button secondary small" disabled={busy}>Create technician link</button>
      {error&&<p className="error" role="alert">{error}</p>}
      {link&&<label>Private visit link<input value={link} readOnly onFocus={e=>e.target.select()}/></label>}
    </form>
  </details>;
}
