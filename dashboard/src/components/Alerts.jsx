import { useState } from 'react'
import { api } from '../api.js'
import { fmtDate, fmtTime, prettyPlate } from '../format.js'
import { usePolling } from '../hooks.js'
import { Badge, Card, Empty, ErrorBox } from './ui.jsx'

export default function Alerts({ user }) {
  const [resolved, setResolved] = useState(false)
  const [err, setErr] = useState('')
  const { data, error, reload } = usePolling(
    () => api(`/sites/${user.site_id}/alerts?resolved=${resolved}`), 5000, [resolved])

  async function resolve(id) {
    setErr('')
    try {
      await api(`/sites/${user.site_id}/alerts/${id}/resolve`, { method: 'POST' })
      reload()
    } catch (e) { setErr(e.message) }
  }

  return (
    <Card
      title={resolved ? 'Resolved alerts' : 'Open alerts'}
      actions={<button onClick={() => setResolved(!resolved)}>{resolved ? 'Show open' : 'Show resolved'}</button>}
    >
      <ErrorBox msg={error || err} />
      {data?.length === 0 && <Empty>{resolved ? 'Nothing resolved yet.' : 'No open alerts. All clear.'}</Empty>}
      {data?.length > 0 && (
        <div className="table-wrap">
          <table>
            <thead><tr><th>Date</th><th>Time</th><th>Plate</th><th>Alert</th><th /></tr></thead>
            <tbody>
              {data.map((a) => (
                <tr key={a.id}>
                  <td>{fmtDate(a.created_at, user.timezone)}</td>
                  <td>{fmtTime(a.created_at, user.timezone)}</td>
                  <td className="plate">{prettyPlate(a.plate)}</td>
                  <td><Badge>{a.type}</Badge></td>
                  <td>{!resolved && <button onClick={() => resolve(a.id)}>Resolve</button>}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </Card>
  )
}
