const KINDS = {
  // decisions
  allow: 'green', deny: 'red', flag: 'amber',
  // alert types
  unknown_plate: 'red', blacklisted: 'red', double_entry: 'amber', exit_without_entry: 'amber', overstay: 'amber',
  // categories
  resident: 'blue', staff: 'blue', visitor: 'violet', unknown: 'gray',
  // pass states / visit status
  active: 'green', upcoming: 'blue', expired: 'gray', revoked: 'red',
  open: 'green', closed: 'gray', auto_closed: 'amber',
}

export function Badge({ children, kind }) {
  const color = KINDS[kind ?? children] || 'gray'
  return <span className={`badge badge-${color}`}>{String(children).replace(/_/g, ' ')}</span>
}

export const ErrorBox = ({ msg }) => (msg ? <div className="error">{msg}</div> : null)

export const Empty = ({ children }) => <p className="empty">{children}</p>

export function Card({ title, children, actions }) {
  return (
    <section className="card">
      {(title || actions) && (
        <header className="card-head">
          <h2>{title}</h2>
          <div>{actions}</div>
        </header>
      )}
      {children}
    </section>
  )
}
