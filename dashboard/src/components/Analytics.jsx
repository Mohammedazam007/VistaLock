import { useState } from 'react'
import { api } from '../api.js'
import { usePolling } from '../hooks.js'
import { Card, ErrorBox } from './ui.jsx'

// Peak hours: entries per hour of day (site timezone), drawn as plain SVG bars.
export default function Analytics({ user }) {
  const [days, setDays] = useState(30)
  const { data, error } = usePolling(() => api(`/sites/${user.site_id}/analytics/hourly?days=${days}`), 0, [days])
  const hours = data?.hours || []
  const max = Math.max(1, ...hours.map((h) => h.entries))
  const total = hours.reduce((a, h) => a + h.entries, 0)
  const peak = hours.reduce((best, h) => (h.entries > best.entries ? h : best), { hour: 0, entries: 0 })

  const W = 720, H = 220, pad = 28, bw = (W - pad * 2) / 24
  return (
    <Card
      title="Peak hours"
      actions={
        <select value={days} onChange={(e) => setDays(Number(e.target.value))}>
          <option value={7}>Last 7 days</option>
          <option value={30}>Last 30 days</option>
          <option value={90}>Last 90 days</option>
        </select>
      }
    >
      <ErrorBox msg={error} />
      {data && (
        <>
          <p className="muted">
            {total === 0 ? 'No entries in this period.' : `${total} entries · busiest hour ${String(peak.hour).padStart(2, '0')}:00 (${peak.entries} entries)`}
          </p>
          <svg viewBox={`0 0 ${W} ${H}`} className="chart" role="img" aria-label="Entries per hour of day">
            {hours.map((h) => {
              const bh = (h.entries / max) * (H - pad * 2)
              return (
                <g key={h.hour}>
                  <rect x={pad + h.hour * bw + 2} y={H - pad - bh} width={bw - 4} height={bh} rx="3" className={h.hour === peak.hour && total ? 'bar peak' : 'bar'}>
                    <title>{`${String(h.hour).padStart(2, '0')}:00 — ${h.entries} entries`}</title>
                  </rect>
                  {h.hour % 3 === 0 && <text x={pad + h.hour * bw + bw / 2} y={H - 8} textAnchor="middle" className="axis">{String(h.hour).padStart(2, '0')}</text>}
                </g>
              )
            })}
            <line x1={pad} x2={W - pad} y1={H - pad} y2={H - pad} className="axis-line" />
          </svg>
        </>
      )}
    </Card>
  )
}
