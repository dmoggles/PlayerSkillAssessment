import { lazy, Suspense, useEffect, useRef, useState } from 'react'
import { createBrowserRouter, Link, Navigate, Route, RouterProvider, Routes, useNavigate, useParams } from 'react-router-dom'
// Each page loads on first use, so a player's or parent's link does not download the coach dashboard.
const CoachDashboard = lazy(() => import('./CoachDashboard'))
const PlayerPage = lazy(() => import('./PlayerPage'))
const SharedReportPage = lazy(() => import('./SharedReportPage'))
import UpdateBanner from './UpdateBanner'
import { APP_NAME, BrandMark, Wordmark } from './brand'
import { acceptInvite, errorMessage, forgotPassword, getInvite, login, logout, register, resendVerification, resetPassword, restoreSession, verify } from './api'
import './App.css'

const errorText = errorMessage

function AuthForm({ onSignedIn, embedded = false, initialEmail = '' }) {
  const [mode, setMode] = useState('login')
  const [email, setEmail] = useState(initialEmail)
  const [password, setPassword] = useState('')
  const [message, setMessage] = useState('')
  const [busy, setBusy] = useState(false)

  async function submit(event) {
    event.preventDefault()
    setBusy(true)
    setMessage('')
    try {
      if (mode === 'login') onSignedIn(await login(email, password))
      if (mode === 'forgot') {
        setMessage((await forgotPassword(email)).message)
      }
      if (mode === 'resend') setMessage((await resendVerification(email)).message)
    } catch (error) {
      setMessage(errorText(error))
    } finally {
      setBusy(false)
    }
  }

  return <div className={embedded ? 'auth-embedded' : 'page login-page public-page'}>
    {!embedded && <><div className="public-brand"><BrandMark tone="light" size={44} /><Wordmark tone="light" /></div><h1>Coach workspace</h1></>}
    <h2>{mode === 'login' ? 'Coach sign in' : mode === 'resend' ? 'Resend verification' : 'Reset password'}</h2>
    <form onSubmit={submit} className="stack">
      <label className="field">Email<input type="email" autoComplete="email" required value={email} onChange={e => setEmail(e.target.value)} /></label>
      {mode !== 'forgot' && mode !== 'resend' && <label className="field">Password<input type="password" minLength={12} autoComplete="current-password" required value={password} onChange={e => setPassword(e.target.value)} /></label>}
      <button className="submit-btn" disabled={busy}>{busy ? 'Working…' : mode === 'login' ? 'Sign in' : mode === 'resend' ? 'Resend link' : 'Send reset link'}</button>
    </form>
    {message && <p role="status" className="notice">{message}</p>}
    {!embedded && <p className="invite-only-note">New to {APP_NAME}? It's invitation-only for now: ask a coach at your club to invite you.</p>}
    <div className="inline-row"><button className="link-btn" onClick={() => { setMode('login'); setMessage('') }}>Sign in</button><button className="link-btn" onClick={() => { setMode('resend'); setMessage('') }}>Resend verification</button><button className="link-btn" onClick={() => { setMode('forgot'); setMessage('') }}>Forgot password</button></div>
  </div>
}

function VerifyPage() {
  const { token } = useParams()
  const [message, setMessage] = useState('Verifying…')
  const started = useRef(false)
  useEffect(() => { if (started.current) return; started.current = true; verify(token).then(() => setMessage('Account verified. You can sign in now.')).catch(e => setMessage(errorText(e))) }, [token])
  return <div className="page public-page"><div className="public-brand"><BrandMark tone="light" size={44} /><Wordmark tone="light" /></div><h1>Account verification</h1><section className="public-card"><p role="status">{message}</p><Link to="/">Sign in</Link></section></div>
}

function ResetPage() {
  const { token } = useParams()
  const [password, setPassword] = useState('')
  const [message, setMessage] = useState('')
  async function submit(event) { event.preventDefault(); try { await resetPassword(token, password); setMessage('Password changed. Sign in now.') } catch (e) { setMessage(errorText(e)) } }
  return <div className="page public-page"><div className="public-brand"><BrandMark tone="light" size={44} /><Wordmark tone="light" /></div><h1>Reset password</h1><form onSubmit={submit} className="stack"><label className="field">New password<input type="password" minLength={12} required value={password} onChange={e => setPassword(e.target.value)} /></label><button className="submit-btn">Save password</button></form>{message && <p role="status" className="notice">{message}</p>}<Link to="/">Sign in</Link></div>
}

// An invitation link: join the team when signed in as the invited coach, otherwise create the account (or sign in).
function InvitePage({ user, onSignedIn }) {
  const { token } = useParams()
  const navigate = useNavigate()
  const [invite, setInvite] = useState(null)
  const [message, setMessage] = useState('')
  const [password, setPassword] = useState('')
  const [busy, setBusy] = useState(false)
  useEffect(() => { getInvite(token).then(setInvite).catch(e => setInvite({ error: errorText(e) })) }, [token])
  const destination = invite?.kind === 'site' ? '/app/settings' : '/app/assessment'

  async function accept() { try { await acceptInvite(token); navigate(destination) } catch (e) { setMessage(errorText(e)) } }
  async function createAccount(event) {
    event.preventDefault()
    setBusy(true)
    setMessage('')
    try {
      await register(invite.email, password, token)
      onSignedIn(await login(invite.email, password))
      navigate(destination)
    } catch (e) { setMessage(errorText(e)) } finally { setBusy(false) }
  }

  const title = invite?.kind === 'site' ? `Welcome to ${APP_NAME}` : invite?.team ? `Join ${invite.team}` : 'Team invitation'
  let body
  if (!invite) body = <section className="public-card"><p role="status">Checking your invitation…</p></section>
  else if (invite.error) body = <section className="public-card"><p role="alert" className="error">{invite.error}</p><Link to="/">Go to sign in</Link></section>
  else if (user && user.email !== invite.email) body = <section className="public-card"><p>This invitation is for {invite.email}, but you're signed in as {user.email}. Sign out, then open the link again.</p></section>
  else if (user && invite.kind === 'team') body = <section className="public-card"><p>Signed in as {user.email}</p><button className="submit-btn" onClick={accept}>Join {invite.team}</button></section>
  else if (user) body = <section className="public-card"><p>You're signed in as {user.email}.</p><Link to={destination}>Set up your team</Link></section>
  else if (invite.account_exists) body = <><p className="invite-lead">You already have an account. Sign in to {invite.kind === 'team' ? `join ${invite.team}` : 'continue'}.</p><AuthForm onSignedIn={onSignedIn} embedded initialEmail={invite.email} /></>
  else body = <form onSubmit={createAccount} className="stack">
    <p className="invite-lead">{invite.kind === 'team' ? `You've been invited to coach ${invite.team}.` : 'Create your account, then set up your team.'}</p>
    <label className="field">Email<input type="email" value={invite.email} readOnly /></label>
    <label className="field">Choose a password<input type="password" minLength={12} autoComplete="new-password" required value={password} onChange={e => setPassword(e.target.value)} /><small>At least 12 characters</small></label>
    <button className="submit-btn" disabled={busy}>{busy ? 'Creating account…' : invite.kind === 'team' ? `Create account and join` : 'Create account'}</button>
  </form>
  return <div className="page public-page login-page"><div className="public-brand"><BrandMark tone="light" size={44} /><Wordmark tone="light" /></div><h1>{title}</h1>{body}{message && <p role="alert" className="error">{message}</p>}</div>
}

function Shell() {
  const [user, setUser] = useState(null)
  const [loading, setLoading] = useState(true)
  useEffect(() => { restoreSession().then(setUser).catch(() => {}).finally(() => setLoading(false)) }, [])
  if (loading) return <div className="page">Loading…</div>
  return <Suspense fallback={<div className="page">Loading…</div>}><Routes>
    <Route path="/self/:token" element={<PlayerPage />} />
    <Route path="/report/:token" element={<SharedReportPage />} />
    <Route path="/verify/:token" element={<VerifyPage />} />
    <Route path="/reset/:token" element={<ResetPage />} />
    <Route path="/invite/:token" element={<InvitePage user={user} onSignedIn={setUser} />} />
    <Route path="/" element={user ? <Navigate to="/app/assessment" replace /> : <AuthForm onSignedIn={setUser} />} />
    <Route path="/app/:area" element={user ? <CoachDashboard user={user} onLogout={async () => { try { await logout() } finally { setUser(null) } }} /> : <AuthForm onSignedIn={setUser} />} />
    <Route path="*" element={<Navigate to="/" replace />} />
  </Routes></Suspense>
}

const router = createBrowserRouter([{ path: '*', element: <Shell /> }])
export default function App() { return <><UpdateBanner /><RouterProvider router={router} /></> }
