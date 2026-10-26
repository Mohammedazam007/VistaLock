// All times are shown in the SITE's timezone, with the date (not just the time).
const opts = (tz, o) => new Intl.DateTimeFormat('en-IN', { timeZone: tz, ...o })

export const fmtDate = (iso, tz) => (iso ? opts(tz, { day: '2-digit', month: 'short', year: 'numeric' }).format(new Date(iso)) : '—')
export const fmtTime = (iso, tz) => (iso ? opts(tz, { hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false }).format(new Date(iso)) : '—')
export const fmtDateTime = (iso, tz) => (iso ? `${fmtDate(iso, tz)} ${fmtTime(iso, tz)}` : '—')

export function fmtDuration(seconds) {
  if (seconds == null) return '—'
  const s = Math.max(0, Math.round(seconds))
  const d = Math.floor(s / 86400), h = Math.floor((s % 86400) / 3600), m = Math.floor((s % 3600) / 60)
  if (d) return `${d}d ${h}h ${m}m`
  if (h) return `${h}h ${m}m`
  if (m) return `${m}m ${s % 60}s`
  return `${s}s`
}

// "TS09AB1234" -> "TS 09 AB 1234" for readability
export function prettyPlate(p) {
  const m = /^([A-Z]{2})(\d{1,2})([A-Z]{1,3})(\d{1,4})$/.exec(p || '')
  return m ? m.slice(1).join(' ') : p
}

export function downloadCsv(filename, rows) {
  const esc = (v) => `"${String(v ?? '').replace(/"/g, '""')}"`
  const csv = rows.map((r) => r.map(esc).join(',')).join('\n')
  const a = document.createElement('a')
  a.href = URL.createObjectURL(new Blob([csv], { type: 'text/csv' }))
  a.download = filename
  a.click()
  URL.revokeObjectURL(a.href)
}
