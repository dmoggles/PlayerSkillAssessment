import { useEffect } from 'react'
import { Link } from 'react-router-dom'
import { APP_NAME } from '../brand'
import PublicLayout from './PublicLayout'
import RequestAccess from './RequestAccess'

// What the app does, in the order a coach uses it.
const STEPS = [
  { title: 'Assess', text: "Rate each player on your club's skill matrix, from 1 to 5 against what's expected at their age. Notes and earlier ratings sit alongside, so you can see how they've moved." },
  { title: 'Choose a focus', text: 'The app suggests what each player should work on next, from their ratings and position. You agree two or three priorities, with the player if you like.' },
  { title: 'Plan', text: 'Each priority gets drills at the right level, from a library with animated diagrams and easier and harder versions, for training and for home.' },
  { title: 'Review', text: "Check in during the development cycle, then reassess. Each player's progress shows period by period, and the team's picture shows where to spend training time." },
]

const FEATURES = [
  { title: 'Players have a say', text: 'Send a player a private link to rate themselves. Their view sits next to yours, so the conversation starts from what both of you think.' },
  { title: 'Reports for players and parents', text: "Share a player's report and practice plan through a private link that expires: no app to install and no account to create." },
  { title: "Your club's skill matrix", text: 'Start from the built-in matrix and adapt it: rename skills, describe the levels your way, add or retire skills, and publish a new version when you are ready.' },
  { title: 'Built for coaching teams', text: 'Several coaches per team, owners who manage access, and an activity log of who changed what.' },
]

const SCREENS = [
  { src: '/landing/plan.jpg', width: 1300, height: 940, alt: 'A four-week plan: for 1v1 attacking, a drill at training and a drill at home, each stepping up after two weeks', caption: "A player's four-week plan" },
  { src: '/landing/progress.jpg', width: 1300, height: 973, alt: "A table of a player's ratings for each skill across three periods, with the change", caption: "Each player's progress, period by period" },
  { src: '/landing/drill.jpg', width: 1300, height: 1122, alt: 'A drill page with its easier and harder variations and an animated diagram', caption: 'Drills with animated diagrams and easier and harder versions' },
]

// The public front page: what TapLine IDP is, how it works, and how a club gets access.
export default function Landing({ user }) {
  useEffect(() => { document.title = `${APP_NAME}: individual development plans for grassroots football` }, [])
  return <PublicLayout user={user}>
    <section className="hero">
      <div className="hero-inner">
        <div className="hero-copy">
          <p className="eyebrow">For grassroots football coaches</p>
          <h1>A development plan for every player</h1>
          <p className="hero-lead">{APP_NAME} helps coaches assess each player's skills, agree what they should work on next, and give them a plan with drills, then follow their progress through the season.</p>
          <div className="hero-actions">
            <a className="button button-lime" href="#request-access">Request access</a>
            {user ? <Link className="button button-ghost" to="/app/assessment">Open your workspace</Link> : <Link className="button button-ghost" to="/sign-in">Sign in</Link>}
          </div>
        </div>
        <Screen {...SCREENS[0]} hero />
      </div>
    </section>

    <section id="how-it-works" className="site-section">
      <h2>How it works</h2>
      <p className="section-lead">Four steps, repeated each development cycle.</p>
      <ol className="steps">{STEPS.map((step, i) => <li key={step.title}><span className="step-number" aria-hidden="true">{i + 1}</span><h3>{step.title}</h3><p>{step.text}</p></li>)}</ol>
      <div className="screens">{SCREENS.slice(1).map(screen => <Screen key={screen.src} {...screen} />)}</div>
    </section>

    <section className="site-section site-section-tint">
      <h2>More than a spreadsheet</h2>
      <div className="features">{FEATURES.map(f => <div key={f.title} className="feature"><h3>{f.title}</h3><p>{f.text}</p></div>)}</div>
    </section>

    <section className="site-section">
      <h2>Careful with children's information</h2>
      <ul className="trust">
        <li><strong>Only what coaching needs.</strong> A player's name, team and age group: no dates of birth, addresses, contact details or photos.</li>
        <li><strong>The club stays in control.</strong> Clubs own their players' information, and can download it or delete it at any time.</li>
        <li><strong>No adverts, no tracking.</strong> One cookie to keep coaches signed in, and nothing sold or shared for marketing.</li>
        <li><strong>Kept in the UK and EU.</strong> Encrypted connections and backups, under UK data protection law.</li>
      </ul>
      <p className="trust-links"><Link to="/privacy">Privacy notice</Link><Link to="/privacy/players">For players and parents</Link></p>
    </section>

    <section id="request-access" className="site-section site-section-dark">
      <h2>Request access</h2>
      <p className="section-lead">{APP_NAME} is invitation-only while we work with a first group of clubs. Tell us about yours, and we'll be in touch.</p>
      <RequestAccess />
    </section>
  </PublicLayout>
}

// A screenshot in a browser-style frame.
function Screen({ src, width, height, alt, caption, hero = false }) {
  return <figure className={`screen${hero ? ' screen-hero' : ''}`}>
    <div className="screen-frame"><span className="screen-dots" aria-hidden="true"><i /><i /><i /></span><img src={src} width={width} height={height} alt={alt} loading={hero ? 'eager' : 'lazy'} /></div>
    {!hero && <figcaption>{caption}</figcaption>}
  </figure>
}
