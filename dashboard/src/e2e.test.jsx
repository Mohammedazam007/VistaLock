// End-to-end tests: the real React app against the REAL backend (no mocks).
//
// Needs: Postgres + API running on localhost:8000 (or GATESENSE_API), with db/seed.sql loaded
// and `python cv/simulate.py` run on that database (the assertions rely on that data).
//   cd dashboard && npm run test:e2e
import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it } from 'vitest'
import { setToken } from './api.js'
import App from './App.jsx'

async function signIn(email, password) {
  const user = userEvent.setup()
  render(<App />)
  await user.type(await screen.findByLabelText(/email/i), email)
  await user.type(screen.getByLabelText(/password/i), password)
  await user.click(screen.getByRole('button', { name: /sign in/i }))
  return user
}

const tabNames = () => screen.getAllByRole('button').map((b) => b.textContent)

beforeEach(() => setToken(null))   // clears the in-memory token AND sessionStorage

describe('login', () => {
  it('shows an error for a wrong password and stays on the login screen', async () => {
    await signIn('admin@sunrise.test', 'wrong-password')
    expect(await screen.findByText(/invalid email or password/i)).toBeTruthy()
    expect(screen.queryByText(/currently inside/i)).toBeNull()
  })

  it('signs out and returns to the login form', async () => {
    const user = await signIn('guard@sunrise.test', 'guard123')
    await screen.findByText(/currently inside/i)
    await user.click(screen.getByRole('button', { name: /sign out/i }))
    expect(await screen.findByRole('button', { name: /sign in/i })).toBeTruthy()
    expect(sessionStorage.getItem('gs_token')).toBeNull()
  })
})

describe('admin / security view', () => {
  it('shows all tabs, summary cards and who is inside right now', async () => {
    await signIn('admin@sunrise.test', 'admin123')
    await screen.findByText(/currently inside/i)
    for (const t of ['Overview', 'Entry / exit log', 'Decisions', 'Alerts', 'Visitor passes', 'Vehicles', 'Analytics']) {
      expect(tabNames()).toContain(t)
    }
    expect(screen.getByText('Inside now')).toBeTruthy()
    // after simulate.py only the resident who entered twice is still inside
    expect(await screen.findAllByText('TS 09 AB 1234')).not.toHaveLength(0)
    expect(screen.queryByText('TS 08 CD 5678')).toBeNull()   // staff already left
  })

  it('entry/exit log shows plate with entry and exit DATE and TIME plus duration', async () => {
    const user = await signIn('admin@sunrise.test', 'admin123')
    await user.click(await screen.findByRole('button', { name: 'Entry / exit log' }))
    for (const h of ['Plate', 'Entry date', 'Entry time', 'Exit date', 'Exit time', 'Duration']) {
      expect(await screen.findByRole('columnheader', { name: h })).toBeTruthy()
    }
    // staff: in at +8 min, out at +18 min (simulate.py may have been run more than once: any matching row will do)
    const rows = (await screen.findAllByText('TS 08 CD 5678')).map((el) => el.closest('tr'))
    const row = rows.find((r) => r.textContent.includes('10m 0s'))
    expect(row, 'a closed visit lasting 10m 0s').toBeTruthy()
    expect(row.textContent).toMatch(/\d{2} [A-Za-z]{3,4} \d{4}/)   // a date
    expect(row.textContent).toMatch(/\d{2}:\d{2}:\d{2}/)            // a time
  })

  it('alerts tab lists the alert types the simulation produced', async () => {
    const user = await signIn('guard@sunrise.test', 'guard123')
    await user.click(await screen.findByRole('button', { name: 'Alerts' }))
    const table = await screen.findByRole('table')
    for (const kind of ['blacklisted', 'unknown plate', 'double entry', 'exit without entry', 'overstay']) {
      expect(await within(table).findAllByText(kind)).not.toHaveLength(0)
    }
  })

  it('only admins get the "Register a vehicle" form', async () => {
    const guard = await signIn('guard@sunrise.test', 'guard123')
    await guard.click(await screen.findByRole('button', { name: 'Vehicles' }))
    await screen.findByText('Vehicle registry')
    expect(screen.queryByText('Register a vehicle')).toBeNull()
  })
})

describe('resident view', () => {
  it('shows only visitor passes, and lets the resident approve a visitor plate', async () => {
    const user = await signIn('ravi@sunrise.test', 'resident123')
    await screen.findByText(/passes for a-101/i)
    expect(tabNames()).not.toContain('Overview')
    expect(tabNames()).not.toContain('Alerts')
    expect(screen.queryByLabelText(/host unit/i)).toBeNull()   // a resident cannot pick another unit

    await user.type(screen.getByLabelText(/vehicle number/i), 'KA05 MM 7777')
    await user.click(screen.getByRole('button', { name: /approve/i }))
    expect(await screen.findAllByText('KA 05 MM 7777')).not.toHaveLength(0)
  })
})
