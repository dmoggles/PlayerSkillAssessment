// Small pieces shared by the coach dashboard's areas.

export function Section({ title, description, children, className = '' }) {
  return <section className={`panel dashboard-panel ${className}`}>
    <div className="panel-heading"><h2>{title}</h2>{description && <p>{description}</p>}</div>
    {children}
  </section>
}

export function ArchivedNotice({ player, onRestore }) {
  return <div className="archived-notice" role="note">
    <span><strong>{player.name} is archived.</strong> Their records are read-only. Restore them to the squad to make changes.</span>
    <button type="button" onClick={onRestore}>Restore player</button>
  </div>
}

export function NavIcon({ name }) {
  const paths = {
    settings: <><circle cx="12" cy="12" r="3" /><path d="M4 12h2m12 0h2M12 4v2m0 12v2M6.4 6.4l1.4 1.4m8.4 8.4 1.4 1.4m0-11.2-1.4 1.4M7.8 16.2l-1.4 1.4" /></>,
    assessment: <><rect x="5" y="4" width="14" height="17" rx="2" /><path d="M9 4.5V3h6v1.5M8 10h8m-8 4h8m-8 4h5" /></>,
    player: <><circle cx="12" cy="8" r="3" /><path d="M5 20c0-3.4 3.1-6 7-6s7 2.6 7 6" /></>,
    team: <><circle cx="8" cy="9" r="2.5" /><circle cx="16" cy="9" r="2.5" /><path d="M2.5 19c0-3 2.5-5 5.5-5m8 0c3 0 5.5 2 5.5 5M6 20c0-3.3 2.5-5.5 6-5.5s6 2.2 6 5.5" /></>,
    development: <><path d="M4 19h16M6 16l4-4 3 2 5-7M15 7h3v3" /></>,
  }
  return <svg aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">{paths[name]}</svg>
}
