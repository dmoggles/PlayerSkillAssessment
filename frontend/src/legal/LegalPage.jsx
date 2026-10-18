import { useEffect } from 'react'
import { Link } from 'react-router-dom'
import { APP_NAME, BrandMark, Wordmark } from '../brand'
import LegalLinks from './LegalLinks'
import { OPERATOR, PROCESSORS, UPDATED } from './operator'

// The privacy notice, the terms and the notice for players and parents. Clubs control their players' information
// and we process it for them; we control coaches' account information.
const PAGES = {
  privacy: { title: 'Privacy notice', body: PrivacyNotice },
  terms: { title: 'Terms of use', body: Terms },
  players: { title: 'For players and parents', body: PlayersNotice },
}

export default function LegalPage({ page }) {
  const { title, body: Body } = PAGES[page]
  useEffect(() => { document.title = `${title} · ${APP_NAME}` }, [title])
  return <div className="page public-page legal-page">
    <div className="public-brand"><BrandMark tone="light" size={44} /><Wordmark tone="light" /></div>
    <h1>{title}</h1>
    <p className="legal-updated">Last updated {UPDATED}</p>
    <article className="legal-body"><Body /></article>
    <LegalLinks />
  </div>
}

const Contact = () => <a href={`mailto:${OPERATOR.email}`}>{OPERATOR.email}</a>
const Who = () => <>{OPERATOR.name}, a sole trader trading as {OPERATOR.tradingName} ({OPERATOR.address})</>

function Processors() {
  return <table className="legal-table">
    <thead><tr><th>Company</th><th>What it does</th><th>Where</th></tr></thead>
    <tbody>{PROCESSORS.map(p => <tr key={p.name}><td>{p.name}</td><td>{p.role}</td><td>{p.where}</td></tr>)}</tbody>
  </table>
}

function PrivacyNotice() {
  return <>
    <p>{APP_NAME} helps football coaches assess their players' skills and plan each player's development. This notice explains what information it holds, why, who can see it, how long it's kept and your rights. It's written for coaches; players and parents have <Link to="/privacy/players">their own, shorter version</Link>.</p>

    <h2>Who we are</h2>
    <p>{APP_NAME} is run by <Who />. We're registered with the Information Commissioner's Office (ICO), number {OPERATOR.icoNumber}. Contact us about privacy at <Contact />.</p>

    <h2>Two kinds of information, two kinds of responsibility</h2>
    <ul>
      <li><strong>Coaches' accounts.</strong> We decide how account information is used, so we're its <em>controller</em>.</li>
      <li><strong>Players' information.</strong> Each club (or team) using {APP_NAME} decides what to record about its players, so the club is the <em>controller</em> and we're its <em>processor</em>: we hold the information for the club and use it only to run the service for them, under our <Link to="/terms">terms</Link>. If you have a question about a player's information, ask the club first. If you ask us, we'll pass the request on to the club and help them answer it.</li>
    </ul>

    <h2>What we hold about coaches</h2>
    <ul>
      <li>Your email address and your password, stored only as a secure hash that can't be turned back into the password.</li>
      <li>The teams you belong to and your role in each.</li>
      <li>Which coach saved each assessment, plan or report, and a team activity log (for example, who invited whom or deleted a period), which names coaches by email.</li>
      <li>Drills you've liked or disliked.</li>
      <li>Drills your team writes, and which coach added or last changed each. Only your team's coaches see them. If you submit one to the shared library, site admins see it, your note and your team's name.</li>
      <li>Videos you suggest for drills, with your note. Only site admins see who suggested a video or why; if you delete your account, an approved video stays on its drill without your name.</li>
      <li>Security records: your signed-in sessions, and counts of failed sign-ins, kept so we can stop password guessing.</li>
      <li>Our web server's access logs: IP address, browser, the page requested and the time. Links that contain private codes (self-assessment, shared report and invitation links) are left out of them.</li>
    </ul>

    <h2>What clubs record about players</h2>
    <p>On a club's behalf we hold: each player's name, team and age group (the "U" number, not a date of birth), playing positions, coaches' skill ratings and notes, the player's own ratings if the club uses self-assessment, the skills chosen to work on, development plans and check-ins, reports the coach writes, and which team training sessions each player was expected at and came to, with their training group. We don't ask for players' dates of birth, addresses, contact details, photos or health information, and coaches are asked not to write such details in notes.</p>
    <p>{APP_NAME} suggests skills to focus on and drills to practise using fixed rules. Coaches review and change these suggestions; nothing is decided about a player automatically.</p>

    <h2>If you request access</h2>
    <p>When you ask for access on our home page, we keep your name, email address, club, number of teams and anything you write, and email them to our site admins. We use them only to reply about access, on the basis of our legitimate interest in answering you, and delete them 30 days after we've replied (or after 180 days if we never do).</p>

    <h2>Why we use coaches' information, and our lawful basis</h2>
    <ul>
      <li><strong>To provide the service you signed up for</strong> (contract): your account, your teams, and the emails the app needs to send (verification, password reset, invitations).</li>
      <li><strong>To keep the service secure and working</strong> (our legitimate interests in protecting it and its users): sign-in limits, access logs, the team activity log and backups.</li>
    </ul>
    <p>We don't send marketing, show adverts, sell information or use analytics or tracking tools.</p>

    <h2>Who else handles the information</h2>
    <p>Only the coaches in a team can see that team's players. A coach can share a player's report by a private link, which works until it expires (usually four to five weeks; the coach can end it sooner). These companies handle information for us, under contracts that require them to protect it:</p>
    <Processors />
    <p>Resend is a US company. Where information reaches the US, it's protected by the safeguards UK law requires, such as the UK International Data Transfer Addendum or the UK Extension to the EU-US Data Privacy Framework. Otherwise the information stays in the UK and EU. We'll share information with others only if the law requires it.</p>

    <h2>How long we keep it</h2>
    <ul>
      <li><strong>Your account:</strong> until you delete it (Settings, Account). Your teams keep what you recorded, with your email taken off it. Accounts never verified are deleted after 30 days.</li>
      <li><strong>Players' information:</strong> as long as the club keeps it. Team owners can delete a player, or a whole team, at any time; it's removed straight away.</li>
      <li><strong>Activity logs of deleted teams:</strong> 90 days after the team is deleted.</li>
      <li><strong>Access requests:</strong> 30 days after we've replied, or 180 days if we haven't.</li>
      <li><strong>Sign-in sessions:</strong> 7 days. Emailed links expire after 24 hours (verification and password reset) or 7 to 14 days (invitations); self-assessment links after 7 days.</li>
      <li><strong>Access logs:</strong> up to 14 days.</li>
      <li><strong>Backups:</strong> encrypted copies made nightly and before updates. Deleted information drops out of every backup within about three months.</li>
    </ul>

    <h2>Cookies</h2>
    <p>We use one cookie, which keeps you signed in. It's essential to the service, so we don't ask for consent. There are no advertising or analytics cookies, and fonts are served from our own server.</p>
    <h2>Drill videos</h2>
    <p>Drill videos are hosted by YouTube or Vimeo. Nothing loads from them until you press Play. Then the video plays from YouTube's privacy-enhanced player (youtube-nocookie.com) or Vimeo's player with tracking turned off, and YouTube's or Vimeo's own privacy policy applies to it. When a coach suggests a video, our server looks up its title from YouTube or Vimeo, sending only the video's link.</p>

    <h2>How we protect it</h2>
    <p>Connections are encrypted (HTTPS), passwords are hashed, backups are encrypted with a key kept off our servers, servers are kept up to date behind a firewall, and access is limited to the people who run the service.</p>

    <h2>Your rights</h2>
    <p>You can ask for a copy of your information, ask us to correct or delete it, ask us to limit how we use it, object to our using it, or ask for it in a portable form. You can delete your account yourself in Settings. For players' information, the club decides; team owners can export or delete a player's information in Settings. Email <Contact /> and we'll reply within one month.</p>
    <p>If you're unhappy with how we've handled your information, you can complain to the ICO: <a href="https://ico.org.uk/make-a-complaint/">ico.org.uk/make-a-complaint</a>, or call 0303 123 1113. We'd appreciate the chance to put things right first.</p>

    <h2>Changes</h2>
    <p>We'll update this notice when anything changes, and change the date at the top. We'll tell team owners by email about important changes.</p>
  </>
}

function PlayersNotice() {
  return <>
    <p className="legal-lead">Your club uses {APP_NAME} to help your coaches see how you're getting on and plan what to work on next. Here's what that means for your information.</p>

    <h2>What's kept about you</h2>
    <ul>
      <li>Your name, your team and your age group (like U12).</li>
      <li>The positions you play.</li>
      <li>Your coaches' scores and notes on your football skills.</li>
      <li>Your own scores, if your coach sends you a self-assessment link.</li>
      <li>The skills you're working on, and your practice plans.</li>
      <li>Which team training sessions you were expected at and came to, and your group in them.</li>
    </ul>
    <p>It doesn't keep your birthday, address, phone number, email or photos.</p>

    <h2>Who can see it</h2>
    <p>Only the coaches in your team. Your coach can send you or your parents a private link to your report. Anyone with the link can open it until it runs out (usually after four or five weeks), so please don't share it. Your information is never used for adverts and never sold.</p>

    <h2>Videos</h2>
    <p>Some drills in your plan have videos. They come from YouTube or Vimeo, and nothing loads until you press Play. Once a video plays, YouTube or Vimeo can see that someone is watching it.</p>

    <h2>Self-assessment links</h2>
    <p>If your coach sends you a link to score yourself, it's just for you: it works once, for 7 days. Be honest; there are no wrong answers, and it helps your coach help you.</p>

    <h2>Who's in charge of it</h2>
    <p>Your club is. {APP_NAME} (run by {OPERATOR.tradingName}) looks after the information for your club and only uses it to run the app. If you have a question, ask your coach or your club, or ask a parent to ask for you.</p>

    <h2>Your rights</h2>
    <p>You can ask to see what's kept about you, to fix anything that's wrong, or to have it deleted. Ask your coach or club: they can download a copy or delete it. If you're under 13, a parent or carer can ask for you. You can also contact us at <Contact />.</p>
    <p>If you're worried about how your information is being used, you can tell the Information Commissioner's Office (the ICO): <a href="https://ico.org.uk/make-a-complaint/">ico.org.uk/make-a-complaint</a>.</p>

    <h2>How long it's kept</h2>
    <p>Until your club deletes it, for example when you leave. After that it's gone straight away from the app, and from our backup copies within about three months.</p>

    <h2>For parents and carers</h2>
    <p>The club is the controller of your child's information and decides what's recorded; we're its processor. To see, correct or delete your child's information, contact the club: team owners can export or delete a player's data in the app. The full <Link to="/privacy">privacy notice</Link> has the details, including where information is stored and the companies that help us run the service.</p>
  </>
}

function Terms() {
  return <>
    <p>These terms apply when you use {APP_NAME}, run by <Who />. By creating an account you agree to them. If you use it for a club, you're agreeing for the club too, and you confirm the club has authorised you to.</p>

    <h2>The service</h2>
    <p>{APP_NAME} lets coaches assess players' football skills, choose what each player should work on, and build development plans with drills. It's invitation-only. We may change, add or remove features, and we'll tell team owners in advance about changes that matter. These terms don't involve any payment; if we ever introduce charges, we'll tell you first and you can choose whether to continue.</p>

    <h2>Your account</h2>
    <ul>
      <li>Each account is for one person. Keep your password to yourself, and tell us at <Contact /> if you think someone else has used your account.</li>
      <li>You must be 18 or over to have a coach account.</li>
      <li>You can delete your account at any time in Settings.</li>
    </ul>

    <h2>Using it properly</h2>
    <ul>
      <li>Only record players you coach, for their football development.</li>
      <li>Give your players and their parents or carers our <Link to="/privacy/players">notice for players and parents</Link>, or your club's own privacy information that covers {APP_NAME}.</li>
      <li>Keep notes about football. Don't record health, family, safeguarding or other sensitive information here; your club's own processes are the place for that.</li>
      <li>Share report links only with the player and their parents or carers.</li>
      <li>Don't try to access teams you don't belong to, disrupt the service, or copy it.</li>
    </ul>
    <p>We may suspend an account that breaks these terms, and will usually explain why first.</p>

    <h2>Your content</h2>
    <p>What you record belongs to you and your club. You let us store and process it only to run the service for you. You can export a player's information, delete players, or delete a whole team at any time.</p>
    <p>Drills your team writes are your team's, and only its coaches see them. When you submit one to the shared library, you confirm it's yours or your club's to share, and you let us edit it, add diagrams and videos, and publish it in the library for every coach and, through shared reports, players. We don't name you or your team in the library. A drill we've published stays there if you later delete yours.</p>

    <h2>Availability and liability</h2>
    <p>We work to keep {APP_NAME} available and your information safe, with regular encrypted backups, but we can't promise it will always be available or error-free, and it's provided as it is. Suggestions it makes (focus areas, drills) are aids for coaches; coaches decide what's right for their players, including whether a drill is safe for them.</p>
    <p>We're not liable for indirect losses, or for losses caused by anything outside our reasonable control. Nothing in these terms limits liability that can't be limited by law, such as for death or personal injury caused by negligence, or for fraud.</p>

    <h2>Ending</h2>
    <p>You can stop using {APP_NAME} at any time by deleting your teams and your account. If we ever close the service, we'll give team owners at least 30 days' notice to export their information.</p>

    <h2 id="data-processing">Data processing for clubs</h2>
    <p>This section is the agreement UK GDPR (Article 28) requires between a club, as controller of its players' information, and us, as processor.</p>
    <ol>
      <li><strong>What we process.</strong> The player information described in our <Link to="/privacy">privacy notice</Link> (names, teams, age groups, positions, ratings, notes, focus areas, plans and reports), about the club's players, for as long as the club keeps it in {APP_NAME}, for the sole purpose of providing the service.</li>
      <li><strong>Instructions.</strong> We process it only on the club's instructions, which are given by using the app and by these terms, unless the law requires otherwise (in which case we'll tell the club, if the law allows).</li>
      <li><strong>Confidentiality.</strong> Everyone who can access it on our side is bound to keep it confidential.</li>
      <li><strong>Security.</strong> We use appropriate technical and organisational measures, including encrypted connections, hashed passwords, encrypted backups, access controls and timely software updates.</li>
      <li><strong>Sub-processors.</strong> The club authorises the companies listed in our privacy notice. We'll tell team owners before adding or replacing one, so the club can object; we bind each one to the same data protection obligations and remain responsible for them.</li>
      <li><strong>Helping the club.</strong> We help the club answer requests from players and parents (the app lets team owners export and delete a player's information), and with its security, breach and impact-assessment obligations, as far as our role allows.</li>
      <li><strong>Breaches.</strong> We'll tell team owners without undue delay after becoming aware of a breach affecting their players' information, with the details we have.</li>
      <li><strong>Deletion.</strong> When the club deletes a player or a team, we delete their information straight away, and from backups within about three months. If the service closes, team owners can export first and we then delete everything.</li>
      <li><strong>Checks.</strong> We'll give the club the information it reasonably needs to show these obligations are met, and answer reasonable questions about them.</li>
      <li><strong>Transfers.</strong> Information leaves the UK and EU only with the safeguards UK law requires.</li>
    </ol>

    <h2>General</h2>
    <p>We may update these terms; we'll tell team owners about important changes before they take effect. These terms are governed by the law of England and Wales, and its courts have jurisdiction. Questions: <Contact />.</p>
  </>
}
