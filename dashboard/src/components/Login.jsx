import { useState } from 'react'
import { api, setToken } from '../api.js'
import { ErrorBox } from './ui.jsx'

export default function Login({ onLogin }) {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  async function submit(e) {
    e.preventDefault()
    setBusy(true)
    setError('')
    try {
      const r = await api('/auth/login', { method: 'POST', body: { email, password } })
      setToken(r.access_token)
      onLogin(r.user)
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="login-wrap">
      <form className="card login" onSubmit={submit}>
        <h1>GateSense</h1>
        <p className="muted">Vehicle access management</p>
        <label>Email<input type="email" value={email} onChange={(e) => setEmail(e.target.value)} required autoFocus /></label>
        <label>Password<input type="password" value={password} onChange={(e) => setPassword(e.target.value)} required /></label>
        <ErrorBox msg={error} />
        <button className="primary" disabled={busy}>{busy ? 'Signing in…' : 'Sign in'}</button>
        {import.meta.env.DEV && (
          <p className="muted small">Demo: admin@sunrise.test / admin123 · guard@sunrise.test / guard123 · ravi@sunrise.test / resident123</p>
        )}
      </form>
    </div>
  )
}
