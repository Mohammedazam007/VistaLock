// Tiny fetch wrapper. The JWT lives in sessionStorage (cleared when the tab closes).
let token = sessionStorage.getItem('gs_token')

export function setToken(t) {
  token = t
  if (t) sessionStorage.setItem('gs_token', t)
  else sessionStorage.removeItem('gs_token')
}

export const hasToken = () => Boolean(token)

export async function api(path, { method = 'GET', body } = {}) {
  const res = await fetch('/api' + path, {
    method,
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: body ? JSON.stringify(body) : undefined,
  })
  if (res.status === 401 && token) {
    setToken(null)
    window.dispatchEvent(new Event('gs-logout'))   // expired or revoked session
  }
  if (!res.ok) {
    let detail
    try { detail = (await res.json()).detail } catch { /* not JSON */ }
    if (Array.isArray(detail)) detail = detail.map((d) => d.msg).join('; ')   // FastAPI validation errors
    throw new Error(detail || res.statusText)
  }
  return res.json()
}
