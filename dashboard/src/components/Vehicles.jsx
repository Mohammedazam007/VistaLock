import { useState } from 'react'
import { api } from '../api.js'
import { prettyPlate } from '../format.js'
import { usePolling } from '../hooks.js'
import { Badge, Card, Empty, ErrorBox } from './ui.jsx'

export default function Vehicles({ user }) {
  const canEdit = user.role === 'admin'
  const [form, setForm] = useState({ plate: '', owner_name: '', role: 'resident', unit: '' })
  const [error, setError] = useState('')
  const { data, error: loadError, reload } = usePolling(() => api(`/sites/${user.site_id}/vehicles`), 0)
  const set = (k) => (e) => setForm({ ...form, [k]: e.target.value })

  async function add(e) {
    e.preventDefault()
    setError('')
    try {
      await api(`/sites/${user.site_id}/vehicles`, {
        method: 'POST',
        body: { ...form, owner_name: form.owner_name || null, unit: form.unit || null },
      })
      setForm({ plate: '', owner_name: '', role: 'resident', unit: '' })
      reload()
    } catch (err) { setError(err.message) }
  }

  return (
    <>
      {canEdit && (
        <Card title="Register a vehicle">
          <form className="filters" onSubmit={add}>
            <label>Vehicle number<input required placeholder="TS09AB1234" value={form.plate} onChange={set('plate')} /></label>
            <label>Owner<input value={form.owner_name} onChange={set('owner_name')} /></label>
            <label>Unit / dept<input value={form.unit} onChange={set('unit')} /></label>
            <label>Role
              <select value={form.role} onChange={set('role')}>
                <option value="resident">Resident</option>
                <option value="staff">Staff</option>
                <option value="blacklisted">Blacklisted</option>
              </select>
            </label>
            <button className="primary">Add</button>
          </form>
          <ErrorBox msg={error} />
        </Card>
      )}
      <Card title="Vehicle registry">
        <ErrorBox msg={loadError} />
        {data?.length === 0 && <Empty>No vehicles registered.</Empty>}
        {data?.length > 0 && (
          <div className="table-wrap">
            <table>
              <thead><tr><th>Plate</th><th>Owner</th><th>Unit / dept</th><th>Role</th></tr></thead>
              <tbody>
                {data.map((v) => (
                  <tr key={v.id}>
                    <td className="plate">{prettyPlate(v.plate)}</td>
                    <td>{v.owner_name || '—'}</td>
                    <td>{v.unit || '—'}</td>
                    <td><Badge kind={v.role === 'blacklisted' ? 'deny' : v.role}>{v.role}</Badge></td>
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
