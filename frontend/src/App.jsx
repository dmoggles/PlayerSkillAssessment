import { useEffect, useRef, useState } from 'react'
import { createBrowserRouter, Link, Navigate, Route, RouterProvider, Routes, useNavigate, useParams } from 'react-router-dom'
import CoachDashboard from './CoachDashboard'
import PlayerPage from './PlayerPage'
import { acceptInvite, forgotPassword, login, logout, register, resendVerification, resetPassword, restoreSession, verify } from './api'
import './App.css'

function errorText(error) {
  return error.response?.data?.detail ?? 'Request failed. Please try again.'
}

function AuthForm({ onSignedIn, embedded = false }) {
  const [mode, setMode] = useState('login')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [message, setMessage] = useState('')
  const [busy, setBusy] = useState(false)

  async function submit(event) {
    event.preventDefault()
    setBusy(true)
    setMessage('')
    try {
      if (mode === 'login') onSignedIn(await login(email, password))
      if (mode === 'register') setMessage((await register(email, password)).message)
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
    {!embedded && <><p className="eyebrow">Player Skills</p><h1>Coach workspace</h1></>}
    <h2>{mode === 'login' ? 'Coach sign in' : mode === 'register' ? 'Create coach account' : mode === 'resend' ? 'Resend verification' : 'Reset password'}</h2>
    <form onSubmit={submit} className="stack">
      <label className="field">Email<input type="email" autoComplete="email" required value={email} onChange={e => setEmail(e.target.value)} /></label>
      {mode !== 'forgot' && mode !== 'resend' && <label className="field">Password<input type="password" minLength={12} autoComplete={mode === 'register' ? 'new-password' : 'current-password'} required value={password} onChange={e => setPassword(e.target.value)} /></label>}
      <button className="submit-btn" disabled={busy}>{busy ? 'Working…' : mode === 'login' ? 'Sign in' : mode === 'register' ? 'Create account' : mode === 'resend' ? 'Resend link' : 'Send reset link'}</button>
    </form>
    {message && <p role="status" className="notice">{message}</p>}
    <div className="inline-row"><button className="link-btn" onClick={() => { setMode('login'); setMessage('') }}>Sign in</button><button className="link-btn" onClick={() => { setMode('register'); setMessage('') }}>Create account</button><button className="link-btn" onClick={() => { setMode('resend'); setMessage('') }}>Resend verification</button><button className="link-btn" onClick={() => { setMode('forgot'); setMessage('') }}>Forgot password</button></div>
  </div>
}

function VerifyPage() {
  const { token } = useParams()
  const [message, setMessage] = useState('Verifying…')
  const started = useRef(false)
  useEffect(() => { if (started.current) return; started.current = true; verify(token).then(() => setMessage('Account verified. You can sign in now.')).catch(e => setMessage(errorText(e))) }, [token])
  return <div className="page public-page"><p className="eyebrow">Player Skills</p><h1>Account verification</h1><section className="public-card"><p role="status">{message}</p><Link to="/">Sign in</Link></section></div>
}

function ResetPage() {
  const { token } = useParams()
  const [password, setPassword] = useState('')
  const [message, setMessage] = useState('')
  async function submit(event) { event.preventDefault(); try { await resetPassword(token, password); setMessage('Password changed. Sign in now.') } catch (e) { setMessage(errorText(e)) } }
  return <div className="page public-page"><p className="eyebrow">Player Skills</p><h1>Reset password</h1><form onSubmit={submit} className="stack"><label className="field">New password<input type="password" minLength={12} required value={password} onChange={e => setPassword(e.target.value)} /></label><button className="submit-btn">Save password</button></form>{message && <p role="status" className="notice">{message}</p>}<Link to="/">Sign in</Link></div>
}

function InvitePage({ user, onSignedIn }) {
  const { token } = useParams()
  const navigate = useNavigate()
  const [message, setMessage] = useState('')
  async function accept() { try { await acceptInvite(token); navigate('/') } catch (e) { setMessage(errorText(e)) } }
  return <div className="page public-page"><p className="eyebrow">Player Skills</p><h1>Team invitation</h1><section className="public-card">{user ? <><p>Signed in as {user.email}</p><button className="submit-btn" onClick={accept}>Join team</button></> : <p>Sign in or create an account with the invited email address.</p>}{message && <p role="alert" className="error">{message}</p>}</section>{!user && <AuthForm onSignedIn={onSignedIn} embedded />}</div>
}

function Shell() {
  const [user, setUser] = useState(null)
  const [loading, setLoading] = useState(true)
  useEffect(() => { restoreSession().then(setUser).catch(() => {}).finally(() => setLoading(false)) }, [])
  if (loading) return <div className="page">Loading…</div>
  return <Routes>
    <Route path="/self/:token" element={<PlayerPage />} />
    <Route path="/verify/:token" element={<VerifyPage />} />
    <Route path="/reset/:token" element={<ResetPage />} />
    <Route path="/invite/:token" element={<InvitePage user={user} onSignedIn={setUser} />} />
    <Route path="/" element={user ? <Navigate to="/app/assessment" replace /> : <AuthForm onSignedIn={setUser} />} />
    <Route path="/app/:area" element={user ? <CoachDashboard user={user} onLogout={async () => { try { await logout() } finally { setUser(null) } }} /> : <AuthForm onSignedIn={setUser} />} />
    <Route path="*" element={<Navigate to="/" replace />} />
  </Routes>
}

const router = createBrowserRouter([{ path: '*', element: <Shell /> }])
export default function App() { return <RouterProvider router={router} /> }
