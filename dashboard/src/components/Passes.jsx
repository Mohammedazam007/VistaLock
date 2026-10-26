import { useState } from 'react'
import { api } from '../api.js'
import { fmtDate, fmtTime, prettyPlate } from '../format.js'
import { usePolling } from '../hooks.js'
import { Badge, Card, Empty, ErrorBox } from './ui.jsx'

// <input type="datetime-local"> wants local "YYYY-MM-DDTHH:mm"
const toLocalInput = (d) => new Date(d.getTime() - d.getTimezoneOffset() * 60000).toISOString().slice(0, 16)
const freshForm = () => ({
  plate: '', visitor_name: '', host_unit: '',
  from: toLocalInput(new Date()), until: toLocalInput(new Date(Date.now() + 3 * 3600 * 1000)),
})

export default function Passes({ user }) {
  const isResident = user.role === 'resident'
  const [form, setForm] = useState(freshForm)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const { data, error: loadError, reload } = usePolling(() => api(`/sites/${user.site_id}/passes`), 10000)
  const set = (k) => (e) => setForm({ ...form, [k]: e.target.value })

  async function create(e) {
    e.preventDefault()
    setBusy(true)
    setError('')
    try {
      await api(`/sites/${user.site_id}/passes`, {
        method: 'POST',
        body: {
          plate: form.plate,
          visitor_name: form.visitor_name || null,
          host_unit: isResident ? null : form.host_unit || null,   // server forces a resident's own unit
          valid_from: new Date(form.from).toISOString(),
          valid_until: new Date(form.until).toISOString(),
        },
      })
      setForm(freshForm())
      reload()
    } catch (err) { setError(err.message) } finally { setBusy(false) }
  }

  async function revoke(id) {
    setError('')
    try {
      await api(`/sites/${user.site_id}/passes/${id}/revoke`, { method: 'POST' })
      reload()
    } catch (err) { setError(err.message) }
  }

  return (
    <>
      <Card title="Approve a visitor vehicle">
        <p className="muted small">The gate opens for this plate only inside the time window below.</p>
        <form className="filters" onSubmit={create}>
          <label>Vehicle number<input required placeholder="TS09AB1234" value={form.plate} onChange={set('plate')} /></label>
          <label>Visitor name<input value={form.visitor_name} onChange={set('visitor_name')} /></label>
          {!isResident && <label>Host unit<input placeholder="A-101" value={form.host_unit} onChange={set('host_unit')} /></label>}
          <label>Valid from<input type="datetime-local" required value={form.from} onChange={set('from')} /></label>
          <label>Valid until<input type="datetime-local" required value={form.until} onChange={set('until')} /></label>
          <button className="primary" disabled={busy}>Approve</button>
        </form>
        <ErrorBox msg={error || loadError} />
      </Card>

      <Card title={isResident ? `Passes for ${user.unit}` : 'All visitor passes'}>
        {data?.length === 0 && <Empty>No passes yet.</Empty>}
        {data?.length > 0 && (
          <div className="table-wrap">
            <table>
              <thead><tr><th>Plate</th><th>Visitor</th><th>Unit</th><th>From</th><th>Until</th><th>State</th><th /></tr></thead>
              <tbody>
                {data.map((p) => (
                  <tr key={p.id}>
                    <td className="plate">{prettyPlate(p.plate)}</td>
                    <td>{p.visitor_name || '—'}</td>
                    <td>{p.host_unit || '—'}</td>
                    <td>{fmtDate(p.valid_from, user.timezone)} {fmtTime(p.valid_from, user.timezone).slice(0, 5)}</td>
                    <td>{fmtDate(p.valid_until, user.timezone)} {fmtTime(p.valid_until, user.timezone).slice(0, 5)}</td>
                    <td><Badge>{p.state}</Badge></td>
                    <td>{(p.state === 'active' || p.state === 'upcoming') && <button onClick={() => revoke(p.id)}>Revoke</button>}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>
    </>
  )
}
