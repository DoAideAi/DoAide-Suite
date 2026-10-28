export async function api(path, options = {}) {
  const response = await fetch(`/api${path}`, { credentials: 'same-origin', ...options,
    headers: { ...(options.body instanceof FormData ? {} : {'Content-Type':'application/json'}), ...options.headers } });
  const data = await response.json();
  if (!response.ok) {
    const error = new Error(typeof data.detail === 'string' ? data.detail : data.detail?.map?.(e => e.msg).join('; ') || 'The request failed.');
    error.status = response.status; throw error;
  }
  return data;
}
export const post = (path, data, headers={}) => api(path,{method:'POST',body:JSON.stringify(data),headers});
