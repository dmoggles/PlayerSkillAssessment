import { Link } from 'react-router-dom'

// Links to the legal pages, for the sign-in page and Settings. Kept apart from the pages so they load only when opened.
export default function LegalLinks() {
  return <nav className="legal-links" aria-label="Privacy and terms">
    <Link to="/privacy">Privacy</Link><Link to="/privacy/players">For players and parents</Link><Link to="/terms">Terms</Link>
  </nav>
}
