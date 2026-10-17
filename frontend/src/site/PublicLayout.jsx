import { Link } from 'react-router-dom'
import { APP_NAME, BrandMark, Wordmark } from '../brand'
import { OPERATOR } from '../legal/operator'
import './site.css'

// The public site's frame: the landing page and, later, the manual. Signed-in coaches get a way back to their
// workspace instead of "Sign in". `user` is undefined while the session is still being checked.
export default function PublicLayout({ user, children }) {
  return <div className="site">
    <header className="site-header">
      <div className="site-bar">
        <Link to="/" className="site-home" aria-label={`${APP_NAME} home`}><BrandMark tone="dark" size={34} /><Wordmark tone="dark" /></Link>
        <nav className="site-nav" aria-label="Site">
          <a href="/#how-it-works">How it works</a>
          <a href="/#request-access">Request access</a>
          {user ? <Link className="site-cta" to="/app/assessment">Open your workspace</Link> : <Link className="site-cta" to="/sign-in">Sign in</Link>}
        </nav>
      </div>
    </header>
    <main>{children}</main>
    <footer className="site-footer">
      <div className="site-footer-inner">
        <div className="site-footer-brand"><BrandMark tone="dark" size={26} /><span>{APP_NAME}: individual development plans for grassroots football</span></div>
        <nav aria-label="Site links">
          <Link to="/sign-in">Sign in</Link>
          <Link to="/privacy">Privacy</Link>
          <Link to="/privacy/players">For players and parents</Link>
          <Link to="/terms">Terms</Link>
          <a href={`mailto:${OPERATOR.email}`}>Contact</a>
        </nav>
        {/* Who runs the service (name and address) is in the privacy notice and terms, linked above. */}
        <p className="site-legal">© {new Date().getFullYear()} {OPERATOR.tradingName} · ICO registration {OPERATOR.icoNumber}</p>
      </div>
    </footer>
  </div>
}
