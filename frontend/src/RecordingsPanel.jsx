import React, {useState} from 'react';
import {api,post} from './client';

export function RecordingsPanel({record,workflow,onSaved}) {
  const [busy,setBusy]=useState(false),[error,setError]=useState(''),[consent,setConsent]=useState(false);
  async function upload(event) {
    const file=event.target.files[0];if(!file)return;setBusy(true);setError('');
    try {const form=new FormData();form.append('file',file);await api(`/records/${record.id}/recordings`,{method:'POST',body:form});await onSaved();}
    catch(error) {setError(error.message);} finally {setBusy(false);event.target.value='';}
  }
  async function transcribe(file) {
    setBusy(true);setError('');
    try {await post(`/files/${file.id}/transcribe`,{provider_consent:consent});await onSaved();}
    catch(error) {setError(error.message);} finally {setBusy(false);}
  }
  return <section className="resource-card"><h3>Recordings and transcripts</h3>
    <p>Upload WAV, OGG, MP3 or M4A recordings up to 10 MiB. Review the transcript before turning it into an order or procedure steps.</p>
    <label className="upload-box">Upload recording<input type="file" accept=".wav,.ogg,.mp3,.m4a" disabled={busy} onChange={upload}/></label>
    <label><input type="checkbox" checked={consent} onChange={e=>setConsent(e.target.checked)}/> I have permission to send the selected recording to Groq for transcription.</label>
    {workflow.files.filter(f=>f.mime.startsWith('audio/')).map(f=><div className="job-row" key={f.id}><strong>{f.name}</strong><p>{f.extraction_status.replaceAll('-',' ')}</p><button className="button secondary small" disabled={busy||!consent||f.extraction_status==='transcribed-needs-review'} onClick={()=>transcribe(f)}>Queue transcription</button>{f.extracted&&<pre className="extracted-text">{f.extracted}</pre>}</div>)}
    {error&&<p className="error" role="alert">{error}</p>}
  </section>;
}
