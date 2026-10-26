import { useState } from 'react'
import { api } from '../api.js'
import { downloadCsv, fmtDate, fmtDuration, fmtTime, prettyPlate } from '../format.js'
import { usePolling } from '../hooks.js'
import { Badge, Card, Empty, ErrorBox } from './ui.jsx'

export default function Logs({ user }) {
  const tz = user.timezone
  const [form, setForm] = useState({ plate: '', from: '', to: '' })
  const [applied, setApplied] = useState(form)
  const set = (k) => (e) => setForm({ ...form, [k]: e.target.value })

  const { data, error, loading } = usePolling(() => {
    const q = new URLSearchParams({ limit: '500' })
    if (applied.plate.trim()) q.set('plate', applied.plate.trim())
    if (applied.from) q.set('date_from', new Date(`${applied.from}T00:00:00`).toISOString())
    if (applied.to) q.set('date_to', new Date(`${applied.to}T23:59:59`).toISOString())
    return api(`/sites/${user.site_id}/visits?${q}`)
  }, 0, [applied])

  const exportCsv = () =>
    downloadCsv('gatesense-visits.csv', [
      ['Plate', 'Type', 'Entry date', 'Entry time', 'Exit date', 'Exit time', 'Duration (s)', 'Status'],
      ...data.map((v) => [v.plate, v.access_category, fmtDate(v.entry_time, tz), fmtTime(v.entry_time, tz),
        fmtDate(v.exit_time, tz), fmtTime(v.exit_time, tz), v.duration_seconds ?? '', v.status]),
    ])

  return (
    <Card title="Entry / exit log" actions={<button disabled={!data?.length} onClick={exportCsv}>Export CSV</button>}>
      <form className="filters" onSubmit={(e) => { e.preventDefault(); setApplied(form) }}>
        <label>Plate<input placeholder="e.g. TS09" value={form.plate} onChange={set('plate')} /></label>
        <label>From<input type="date" value={form.from} onChange={set('from')} /></label>
        <label>To<input type="date" value={form.to} onChange={set('to')} /></label>
        <button className="primary">Search</button>
        <button type="button" onClick={() => { const empty = { plate: '', from: '', to: '' }; setForm(empty); setApplied(empty) }}>Clear</button>
      </form>
      <ErrorBox msg={error} />
      {!loading && data?.length === 0 && <Empty>No visits match.</Empty>}
      {data?.length > 0 && (
        <div className="table-wrap">
          <table>
            <thead>
              <tr><th>Plate</th><th>Type</th><th>Entry date</th><th>Entry time</th><th>Exit date</th><th>Exit time</th><th>Duration</th><th>Status</th></tr>
            </thead>
            <tbody>
              {data.map((v) => (
                <tr key={v.id}>
                  <td className="plate">{prettyPlate(v.plate)}</td>
                  <td><Badge>{v.access_category}</Badge></td>
                  <td>{fmtDate(v.entry_time, tz)}</td>
                  <td>{fmtTime(v.entry_time, tz)}</td>
                  <td>{fmtDate(v.exit_time, tz)}</td>
                  <td>{fmtTime(v.exit_time, tz)}</td>
                  <td>{fmtDuration(v.duration_seconds)}</td>
                  <td><Badge>{v.status}</Badge></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </Card>
  )
}
