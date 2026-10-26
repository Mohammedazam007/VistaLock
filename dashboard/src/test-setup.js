// The dashboard calls fetch('/api/...'); in dev, Vite's proxy forwards that to the backend.
// Under vitest there is no proxy, so route /api/* straight to the running backend.
const realFetch = globalThis.fetch
const BACKEND = process.env.GATESENSE_API || 'http://localhost:8000'

globalThis.fetch = (url, opts) =>
  realFetch(typeof url === 'string' && url.startsWith('/api') ? BACKEND + url.slice(4) : url, opts)
