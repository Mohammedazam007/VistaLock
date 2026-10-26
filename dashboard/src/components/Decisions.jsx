import { api } from '../api.js'
import { fmtDate, fmtTime, prettyPlate } from '../format.js'
import { usePolling } from '../hooks.js'
import { Badge, Card, Empty, ErrorBox } from './ui.jsx'

// Audit trail: every allow / deny / flag the system made, with the reason.
export default function Decisions({ user }) {
  const { data, error } = usePolling(() => api(`/sites/${user.site_id}/access-logs?limit=200`), 5000)
  return (
    <Card title="Access decisions" actions={<span className="muted small">audit trail · live</span>}>
      <ErrorBox msg={error} />
      {data?.length === 0 && <Empty>No decisions yet.</Empty>}
      {data?.length > 0 && (
        <div className="table-wrap">
          <table>
            <thead><tr><th>Date</th><th>Time</th><th>Plate</th><th>Direction</th><th>Decision</th><th>Reason</th><th>Confidence</th></tr></thead>
            <tbody>
              {data.map((d) => (
                <tr key={d.id}>
                  <td>{fmtDate(d.captured_at, user.timezone)}</td>
                  <td>{fmtTime(d.captured_at, user.timezone)}</td>
                  <td className="plate">{prettyPlate(d.plate)}</td>
                  <td>{d.direction}</td>
                  <td><Badge>{d.decision}</Badge></td>
                  <td>{d.reason.replace(/_/g, ' ')}</td>
                  <td>{d.confidence == null ? '—' : `${Math.round(d.confidence * 100)}%`}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </Card>
  )
}
