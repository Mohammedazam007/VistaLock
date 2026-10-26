import { api } from '../api.js'
import { fmtDate, fmtDuration, fmtTime, prettyPlate } from '../format.js'
import { usePolling } from '../hooks.js'
import { Badge, Card, Empty, ErrorBox } from './ui.jsx'

export default function Overview({ user }) {
  const site = user.site_id
  const summary = usePolling(() => api(`/sites/${site}/summary`), 5000)
  const inside = usePolling(() => api(`/sites/${site}/inside`), 5000)
  const over = usePolling(() => api(`/sites/${site}/overstays`), 15000)
  const overdue = new Set((over.data || []).map((o) => o.plate))
  const s = summary.data

  return (
    <>
      <div className="stats">
        <Stat label="Inside now" value={s?.inside} />
        <Stat label="Visits today" value={s?.visits_today} />
        <Stat label="Denied today" value={s?.denied_today} tone={s?.denied_today ? 'warn' : ''} />
        <Stat label="Open alerts" value={s?.open_alerts} tone={s?.open_alerts ? 'bad' : ''} />
      </div>

      <Card title="Currently inside" actions={<span className="muted small">live · refreshes every 5 s</span>}>
        <ErrorBox msg={inside.error} />
        {inside.data?.length === 0 && <Empty>No vehicles inside right now.</Empty>}
        {inside.data?.length > 0 && (
          <div className="table-wrap">
            <table>
              <thead><tr><th>Plate</th><th>Type</th><th>Entry date</th><th>Entry time</th><th>Inside for</th><th /></tr></thead>
              <tbody>
                {inside.data.map((v) => (
                  <tr key={v.id}>
                    <td className="plate">{prettyPlate(v.plate)}</td>
                    <td><Badge>{v.access_category}</Badge></td>
                    <td>{fmtDate(v.entry_time, user.timezone)}</td>
                    <td>{fmtTime(v.entry_time, user.timezone)}</td>
                    <td>{fmtDuration(v.inside_seconds)}</td>
                    <td>{overdue.has(v.plate) && <Badge kind="overstay">overstay</Badge>}</td>
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

const Stat = ({ label, value, tone = '' }) => (
  <div className={`stat ${tone}`}>
    <div className="stat-value">{value ?? '–'}</div>
    <div className="stat-label">{label}</div>
  </div>
)
