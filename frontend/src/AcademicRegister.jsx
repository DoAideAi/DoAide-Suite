import React, {useState} from 'react';
import {api} from './client';

export function AcademicRegister() {
  const [rows,setRows]=useState(null),[error,setError]=useState('');
  return <section className="resource-card"><h3>Academic enrollment register</h3>
    <p>Student, course and enrollment dates for academic staff.</p>
    <button className="button secondary small" onClick={async()=>{setError('');try{setRows(await api('/fees/academic'));}catch(error){setError(error.message);}}}>Load enrollments</button>
    {error&&<p className="error" role="alert">{error}</p>}
    {rows&&<div className="table-scroll"><table><thead><tr><th>Student</th><th>Course</th><th>Reference</th><th>Start</th><th>End</th><th>Status</th></tr></thead><tbody>{rows.map(r=><tr key={r.record_id}><td>{r.student}</td><td>{r.course}</td><td>{r.student_reference}</td><td>{r.start}</td><td>{r.end}</td><td>{r.status}</td></tr>)}</tbody></table>{!rows.length&&<p>No enrollments saved.</p>}</div>}
  </section>;
}
