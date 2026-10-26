import { useEffect, useState } from 'react'
import { api, hasToken, setToken } from './api.js'
import Alerts from './components/Alerts.jsx'
import Analytics from './components/Analytics.jsx'
import Decisions from './components/Decisions.jsx'
import Login from './components/Login.jsx'
import Logs from './components/Logs.jsx'
import Overview from './components/Overview.jsx'
import Passes from './components/Passes.jsx'
import Vehicles from './components/Vehicles.jsx'

const STAFF_TABS = [
  ['overview', 'Overview', Overview],
  ['logs', 'Entry / exit log', Logs],
  ['decisions', 'Decisions', Decisions],
  ['alerts', 'Alerts', Alerts],
  ['passes', 'Visitor passes', Passes],
  ['vehicles', 'Vehicles', Vehicles],
  ['analytics', 'Analytics', Analytics],
]
const TABS = { admin: STAFF_TABS, security: STAFF_TABS, resident: [['passes', 'Visitor passes', Passes]] }

export default function App() {
  const [user, setUser] = useState(null)
  const [booting, setBooting] = useState(hasToken())
  const [tab, setTab] = useState(null)

  // Restore the session after a page refresh
  useEffect(() => {
    if (!hasToken()) return
    api('/auth/me').then(setUser).catch(() => setToken(null)).finally(() => setBooting(false))
  }, [])

  useEffect(() => {
    const out = () => { setUser(null); setTab(null) }
    window.addEventListener('gs-logout', out)
    return () => window.removeEventListener('gs-logout', out)
  }, [])

  if (booting) return <p className="empty">Loading…</p>
  if (!user) return <Login onLogin={setUser} />

  const tabs = TABS[user.role]
  const active = tabs.find(([id]) => id === tab) || tabs[0]
  const Active = active[2]

  return (
    <div className="app">
      <header className="topbar">
        <div>
          <strong>GateSense</strong> <span className="muted">· {user.site_name}</span>
        </div>
        <div className="who">
          <span>{user.full_name || user.email} <span className="muted">({user.role}{user.unit ? ` · ${user.unit}` : ''})</span></span>
          <button onClick={() => { setToken(null); setUser(null); setTab(null) }}>Sign out</button>
        </div>
      </header>
      <nav className="tabs">
        {tabs.map(([id, label]) => (
          <button key={id} className={id === active[0] ? 'tab active' : 'tab'} onClick={() => setTab(id)}>{label}</button>
        ))}
      </nav>
      <main><Active user={user} /></main>
    </div>
  )
}
