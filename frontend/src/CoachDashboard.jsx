import { useCallback, useEffect, useRef, useState } from 'react'
import { useBlocker, useLocation, useNavigate } from 'react-router-dom'
import { activatePeriod, addPlayer, archivePlayer, createPeriod, createTeam, deletePeriod, deleteTeam, errorMessage, getAuditLog, getCoachAssessment, getComparison, getMembers, getPeriodAssessments, getPeriods, getPlayerHistory, getPlayers, getMatrixVersion, getRevisions, getTeams, inviteCoach, issueSelfLink, removeMember, renamePeriod, renamePlayer, restorePlayer, revokeSelfLink, setMemberRole, submitCoachAssessment, updateTeam } from './api'
import SkillForm from './SkillForm'
import MobileAssessment from './MobileAssessment'
import ComparisonView from './ComparisonView'
import SummaryView from './SummaryView'
import ConfirmedPrioritiesPanel from './ConfirmedPrioritiesView'
import PrioritiesView from './PrioritiesView'
import HeatmapView from './HeatmapView'
import ChangePasswordForm from './ChangePasswordForm'
import SelfAssessmentBoard from './SelfAssessmentBoard'
import RevisionHistory from './RevisionHistory'
import MatrixEditor from './MatrixEditor'
import MatrixSummary from './MatrixSummary'
import ReportPanel from './ReportPanel'
import { auditText } from './auditModel'
import { priorityFollowUp } from './followUpModel'
import { ALL_POSITIONS, POSITION_LABELS, FREQUENCIES, sectionsFor, skillSetFor } from './matrix'
import { APP_VERSION } from './version'
import { AREAS, PLAYER_DATA_TABS, PLAYER_GENDERS, assessmentSignature, canManageTeam, formFromAssessment, formSignature, initialPeriodId, initialPlayerId } from './dashboardModel'

const fail = errorMessage

function NavIcon({ name }) {
  const paths = {
    settings: <><circle cx="12" cy="12" r="3" /><path d="M4 12h2m12 0h2M12 4v2m0 12v2M6.4 6.4l1.4 1.4m8.4 8.4 1.4 1.4m0-11.2-1.4 1.4M7.8 16.2l-1.4 1.4" /></>,
    assessment: <><rect x="5" y="4" width="14" height="17" rx="2" /><path d="M9 4.5V3h6v1.5M8 10h8m-8 4h8m-8 4h5" /></>,
    player: <><circle cx="12" cy="8" r="3" /><path d="M5 20c0-3.4 3.1-6 7-6s7 2.6 7 6" /></>,
    team: <><circle cx="8" cy="9" r="2.5" /><circle cx="16" cy="9" r="2.5" /><path d="M2.5 19c0-3 2.5-5 5.5-5m8 0c3 0 5.5 2 5.5 5M6 20c0-3.3 2.5-5.5 6-5.5s6 2.2 6 5.5" /></>,
    development: <><path d="M4 19h16M6 16l4-4 3 2 5-7M15 7h3v3" /></>,
  }
  return <svg aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">{paths[name]}</svg>
}

export function ProgressView({ matrix, history }) {
  const periods = history.filter(row => row.assessments.coach)
  if (!periods.length) return <p className="muted">No coach assessments recorded yet.</p>
  const skillIds = [...new Set(periods.flatMap(row => row.assessments.coach.ratings.map(r => r.skill_id)))]
  const names = Object.fromEntries(matrix.sections.flatMap(section => section.skills.map(skill => [skill.id, skill.label])))
  const score = (row, id) => row.assessments.coach.ratings.find(r => r.skill_id === id)?.score
  const change = id => {
    const first = score(periods[0], id)
    const last = score(periods[periods.length - 1], id)
    return first != null && last != null && periods.length > 1 ? `${last - first > 0 ? '+' : ''}${last - first}` : '—'
  }
  return <div className="history">
    <h3>Progress across periods</h3>
    <div className="desktop-data"><div className="heatmap-scroll"><table className="heatmap-table"><thead><tr><th>Skill</th>{periods.map(row => <th key={row.period_id}>{row.label}</th>)}<th>Change</th></tr></thead><tbody>{skillIds.map(id => <tr key={id}><td>{names[id] ?? id}</td>{periods.map(row => <td key={row.period_id}>{score(row, id) ?? '—'}</td>)}<td>{change(id)}</td></tr>)}</tbody></table></div></div>
    <div className="mobile-data mobile-card-list">{skillIds.map(id => <article className="data-card" key={id}><h4>{names[id] ?? id}</h4><dl>{periods.map(row => <div key={row.period_id}><dt>{row.label}</dt><dd>{score(row, id) ?? '—'}</dd></div>)}<div className="data-card-total"><dt>Change</dt><dd>{change(id)}</dd></div></dl></article>)}</div>
  </div>
}

function Section({ title, description, children, className = '' }) {
  return <section className={`panel dashboard-panel ${className}`}><div className="panel-heading"><h2>{title}</h2>{description && <p>{description}</p>}</div>{children}</section>
}

export function ArchivedNotice({ player, onRestore }) {
  return <div className="archived-notice" role="note"><span><strong>{player.name} is archived.</strong> Their records are read-only. Restore them to the squad to make changes.</span><button type="button" onClick={onRestore}>Restore player</button></div>
}

export default function CoachDashboard({ user, onLogout }) {
  const navigate = useNavigate()
  const location = useLocation()
  const currentArea = AREAS.find(area => location.pathname === `/app/${area.id}`) ?? AREAS[0]
  // Matrix documents by team and version id: each period is rated on its own version, and wording follows the team's player gender.
  const [matrices, setMatrices] = useState({})
  const [teams, setTeams] = useState([])
  const [teamId, setTeamId] = useState('')
  const [players, setPlayers] = useState([])
  const [periods, setPeriods] = useState([])
  const [playerId, setPlayerId] = useState('')
  const [periodId, setPeriodId] = useState('')
  const [coach, setCoach] = useState(null)
  const [comparison, setComparison] = useState(null)
  const [history, setHistory] = useState([])
  const [revisions, setRevisions] = useState([])
  const [heatmap, setHeatmap] = useState([])
  const [playerDataView, setPlayerDataView] = useState('summary')
  const [newTeam, setNewTeam] = useState('')
  const [newPlayer, setNewPlayer] = useState('')
  const [newPeriod, setNewPeriod] = useState('')
  const [inviteEmail, setInviteEmail] = useState('')
  const [members, setMembers] = useState([])
  const [auditEvents, setAuditEvents] = useState(null)
  const [matrixEditorTeam, setMatrixEditorTeam] = useState(null)
  const [link, setLink] = useState('')
  const [message, setMessage] = useState('')
  const [position, setPosition] = useState('defender')
  const [secondary, setSecondary] = useState('')
  const [frequency, setFrequency] = useState('sometimes')
  const [ratings, setRatings] = useState({})
  const [notes, setNotes] = useState({})
  const [assessmentNote, setAssessmentNote] = useState('')
  const [assessmentBaseline, setAssessmentBaseline] = useState(null)
  const [prioritiesDirty, setPrioritiesDirty] = useState(false)
  const [reportDirty, setReportDirty] = useState(false)

  const selectedTeam = teams.find(t => t.id === Number(teamId))
  const selectedPlayer = players.find(p => p.id === Number(playerId))
  const selectedPeriod = periods.find(p => p.id === Number(periodId))
  const versionId = selectedPeriod?.matrix_version_id
  const matrixKey = teamId && versionId ? `${teamId}:${versionId}` : null
  const matrix = matrixKey ? matrices[matrixKey] ?? null : null
  const assessmentDirty = assessmentBaseline !== null && assessmentSignature(position, secondary, frequency, ratings, notes, assessmentNote) !== assessmentBaseline
  const dirty = assessmentDirty || prioritiesDirty || reportDirty
  const blocker = useBlocker(dirty)
  const blockerPrompted = useRef(false)
  const contextDialogRef = useRef(null)

  const applyForm = useCallback(assessment => {
    const form = formFromAssessment(assessment)
    setPosition(form.position); setSecondary(form.secondary); setFrequency(form.frequency)
    setRatings(form.ratings); setNotes(form.notes); setAssessmentNote(form.note)
    setAssessmentBaseline(formSignature(form))
  }, [])
  const restoreAssessment = useCallback(() => applyForm(coach), [applyForm, coach])

  useEffect(() => {
    if (blocker.state !== 'blocked') { blockerPrompted.current = false; return }
    if (blockerPrompted.current) return
    blockerPrompted.current = true
    queueMicrotask(() => {
      if (window.confirm('Discard unsaved changes?')) {
        restoreAssessment()
        setPrioritiesDirty(false); setReportDirty(false)
        blocker.proceed()
      } else blocker.reset()
    })
  }, [blocker, restoreAssessment])

  useEffect(() => {
    if (!dirty) return
    const beforeUnload = event => { event.preventDefault(); event.returnValue = '' }
    window.addEventListener('beforeunload', beforeUnload)
    return () => window.removeEventListener('beforeunload', beforeUnload)
  }, [dirty])

  useEffect(() => {
    const phone = window.matchMedia('(max-width: 760px)')
    const closeOnDesktop = () => { if (!phone.matches && contextDialogRef.current?.open) contextDialogRef.current.close() }
    phone.addEventListener('change', closeOnDesktop)
    return () => phone.removeEventListener('change', closeOnDesktop)
  }, [])

  function confirmDiscard() {
    if (!dirty) return true
    if (!window.confirm('Discard unsaved changes?')) return false
    restoreAssessment()
    setPrioritiesDirty(false); setReportDirty(false)
    return true
  }

  function chooseTeam(id) {
    if (confirmDiscard()) selectTeam(id)
  }
  function selectTeam(id) {
    setAuditEvents(null)
    setTeamId(id); setPlayers([]); setPeriods([]); setPlayerId(''); setPeriodId('')
    setCoach(null); setComparison(null); setHistory([]); setRevisions([]); setHeatmap([]); setLink(''); setAssessmentBaseline(null)
  }
  function choosePlayer(id) {
    if (!confirmDiscard()) return
    setPlayerId(id); setCoach(null); setComparison(null); setHistory([]); setRevisions([]); setLink(''); setRatings({}); setNotes({}); setAssessmentNote(''); setAssessmentBaseline(null)
  }
  function choosePeriod(id) {
    if (confirmDiscard()) selectPeriod(id)
  }
  function selectPeriod(id) {
    setPeriodId(id); setCoach(null); setComparison(null); setHistory([]); setRevisions([]); setHeatmap([]); setLink(''); setRatings({}); setNotes({}); setAssessmentNote(''); setAssessmentBaseline(null)
  }

  useEffect(() => {
    getTeams().then(rows => { setTeams(rows); if (rows.length) setTeamId(String(rows[0].id)) }).catch(e => setMessage(fail(e)))
  }, [])

  useEffect(() => {
    if (!matrixKey || matrices[matrixKey]) return
    let live = true
    getMatrixVersion(teamId, versionId).then(doc => { if (live) setMatrices(previous => ({ ...previous, [matrixKey]: doc })) }).catch(e => { if (live) setMessage(fail(e)) })
    return () => { live = false }
  }, [teamId, versionId, matrixKey, matrices])

  useEffect(() => {
    if (!teamId) return
    let live = true
    Promise.all([getPlayers(teamId), getPeriods(teamId)]).then(([roster, rounds]) => {
      if (!live) return
      setPlayers(roster); setPeriods(rounds)
      setPlayerId(initialPlayerId(roster))
      setPeriodId(initialPeriodId(rounds))
    }).catch(e => { if (live) setMessage(fail(e)) })
    getMembers(teamId).then(value => { if (live) setMembers(value) }).catch(() => { if (live) setMembers([]) })
    return () => { live = false }
  }, [teamId])

  useEffect(() => {
    if (!teamId || !playerId || !periodId) return
    let live = true
    Promise.allSettled([getCoachAssessment(teamId, playerId, periodId), getComparison(teamId, playerId, periodId), getPlayerHistory(teamId, playerId)]).then(([assessmentResult, comparisonResult, historyResult]) => {
      if (!live) return
      if (comparisonResult.status === 'fulfilled') setComparison(comparisonResult.value)
      if (historyResult.status === 'fulfilled') setHistory(historyResult.value)
      if (assessmentResult.status !== 'fulfilled') { setMessage(fail(assessmentResult.reason)); return }
      const assessment = assessmentResult.value
      setCoach(assessment)
      applyForm(assessment)
      if (assessment) getRevisions(teamId, assessment.id).then(value => { if (live) setRevisions(value) }).catch(() => {})
    })
    return () => { live = false }
  }, [teamId, playerId, periodId, applyForm])

  useEffect(() => {
    if (currentArea.id !== 'team-data' || !teamId || !periodId) return
    let live = true
    getPeriodAssessments(teamId, periodId).then(value => { if (live) setHeatmap(value) }).catch(e => { if (live) setMessage(fail(e)) })
    return () => { live = false }
  }, [currentArea.id, teamId, periodId])

  async function createTeamAction(event) {
    event.preventDefault()
    try { const team = await createTeam(newTeam.trim()); setTeams(previous => [...previous, team]); chooseTeam(String(team.id)); setNewTeam(''); setMessage('Team created.') } catch (e) { setMessage(fail(e)) }
  }
  async function createPlayerAction(event) {
    event.preventDefault()
    try { const player = await addPlayer(teamId, newPlayer.trim()); setPlayers(previous => [...previous, player]); choosePlayer(String(player.id)); setNewPlayer(''); setMessage('Player added.') } catch (e) { setMessage(fail(e)) }
  }
  async function createPeriodAction(event) {
    event.preventDefault()
    try { const period = await createPeriod(teamId, newPeriod.trim()); setPeriods(previous => [period, ...previous.map(p => ({ ...p, is_active: false }))]); choosePeriod(String(period.id)); setNewPeriod(''); setMessage('Period created.') } catch (e) { setMessage(fail(e)) }
  }
  async function save(event) {
    event.preventDefault()
    const skills = sectionsFor(matrix, skillSetFor(position)).flatMap(section => section.skills)
    try {
      const assessment = await submitCoachAssessment(teamId, {
        player_id: Number(playerId), period_id: Number(periodId), version: coach?.version ?? 0,
        primary_position: position, secondary_position: secondary || null,
        secondary_position_frequency: secondary ? frequency : null,
        note: assessmentNote.trim() || null,
        ratings: skills.map(skill => ({ skill_id: skill.id, score: ratings[skill.id] ?? null, note: notes[skill.id]?.trim() || null })),
      })
      setCoach(assessment); setMessage('Assessment saved.')
      applyForm(assessment)
      getComparison(teamId, playerId, periodId).then(setComparison)
      getPlayerHistory(teamId, playerId).then(setHistory)
      getRevisions(teamId, assessment.id).then(setRevisions)
    } catch (e) { setMessage(fail(e)) }
  }
  async function makeLink() {
    try { const value = await issueSelfLink(teamId, playerId, periodId); setLink(value.url); setMessage('New link created. Copy it now; it will not be shown again.') } catch (e) { setMessage(fail(e)) }
  }
  async function renamePeriodAction(period) {
    const label = window.prompt('New period label', period.label)
    if (!label?.trim() || label.trim() === period.label) return
    try { const updated = await renamePeriod(teamId, period.id, label.trim()); setPeriods(previous => previous.map(p => p.id === updated.id ? updated : p)) } catch (e) { setMessage(fail(e)) }
  }
  async function deletePeriodAction(period) {
    const selected = Number(periodId) === period.id
    if (!window.confirm(`Delete ${period.label}? Every coach assessment, self-assessment and priority recorded in this period is permanently deleted.`)) return
    if (selected && !confirmDiscard()) return
    try {
      await deletePeriod(teamId, period.id)
      const rounds = await getPeriods(teamId)
      setPeriods(rounds)
      if (selected) selectPeriod(initialPeriodId(rounds))
      setMessage('Period deleted.')
    } catch (e) { setMessage(fail(e)) }
  }
  async function restorePlayerAction(player) {
    try { const updated = await restorePlayer(teamId, player.id); setPlayers(previous => previous.map(p => p.id === updated.id ? updated : p)); setMessage(`${updated.name} restored to the squad.`) } catch (e) { setMessage(fail(e)) }
  }
  function dropTeam(id) {
    const remaining = teams.filter(t => t.id !== id)
    setTeams(remaining)
    setMembers([])
    selectTeam(remaining.length ? String(remaining[0].id) : '')
  }
  async function changeRoleAction(member, role) {
    const self = member.email === user.email
    const question = role === 'owner'
      ? `Make ${member.email} an owner? Owners can change team settings, manage members and delete the team.`
      : self ? 'Step down to coach? You will no longer be able to manage this team.' : `Change ${member.email} to a coach?`
    if (!window.confirm(question)) return
    try {
      const updated = await setMemberRole(teamId, member.user_id, role)
      setMembers(previous => previous.map(m => m.user_id === updated.user_id ? updated : m))
      if (self) setTeams(previous => previous.map(t => t.id === Number(teamId) ? { ...t, role } : t))
    } catch (e) { setMessage(fail(e)) }
  }
  async function removeMemberAction(member) {
    const self = member.email === user.email
    if (!window.confirm(self ? `Leave ${selectedTeam.name}? You will lose access to it.` : `Remove ${member.email} from this team?`)) return
    if (self && !confirmDiscard()) return
    try {
      await removeMember(teamId, member.user_id)
      if (self) { dropTeam(Number(teamId)); setMessage(`You left ${selectedTeam.name}.`) } else setMembers(previous => previous.filter(row => row.user_id !== member.user_id))
    } catch (e) { setMessage(fail(e)) }
  }
  async function deleteTeamAction() {
    const name = window.prompt(`This permanently deletes ${selectedTeam.name} with all its players, periods, assessments and priorities, and removes every member's access. Type the team name to confirm.`)
    if (name == null) return
    if (name.trim() !== selectedTeam.name) { setMessage('Team name did not match. Nothing was deleted.'); return }
    if (!confirmDiscard()) return
    try { await deleteTeam(teamId, name.trim()); dropTeam(Number(teamId)); setMessage(`${selectedTeam.name} deleted.`) } catch (e) { setMessage(fail(e)) }
  }
  async function revokeLink() { try { await revokeSelfLink(teamId, playerId, periodId); setLink(''); setMessage('Link revoked.') } catch (e) { setMessage(fail(e)) } }

  const context = <div className="context-controls">
    <label className="field">Team<select value={teamId} onChange={event => chooseTeam(event.target.value)}><option value="">Select team</option>{teams.map(team => <option key={team.id} value={team.id}>{team.name}</option>)}</select></label>
    {selectedTeam && <label className="field">Period<select value={periodId} onChange={event => choosePeriod(event.target.value)}><option value="">Select period</option>{periods.map(period => <option key={period.id} value={period.id}>{period.label}{period.is_active ? ' · active' : ''}</option>)}</select></label>}
    {selectedTeam && ['assessment', 'player-data', 'development'].includes(currentArea.id) && <label className="field">Player<select value={playerId} onChange={event => choosePlayer(event.target.value)}><option value="">Select player</option>{players.map(player => <option key={player.id} value={player.id}>{player.name}{player.active ? '' : ' · archived'}</option>)}</select></label>}
  </div>
  const needsPlayer = ['assessment', 'player-data', 'development'].includes(currentArea.id)
  const contextPrimary = needsPlayer && selectedPlayer ? selectedPlayer.name : selectedTeam?.name ?? 'Choose a team'
  const contextSecondary = [needsPlayer && selectedPlayer ? selectedTeam?.name : null, selectedPeriod?.label].filter(Boolean).join(' · ') || 'Tap to choose team and period'

  return <div className="dashboard-shell">
    <aside className="dashboard-sidebar"><div className="brand"><span className="brand-mark">PS</span><div><strong>Player Skills</strong><span>Coach workspace</span></div></div><nav aria-label="Main navigation" className="side-nav">{AREAS.map(area => <button key={area.id} type="button" className={area.id === currentArea.id ? 'active' : ''} aria-current={area.id === currentArea.id ? 'page' : undefined} onClick={() => navigate(`/app/${area.id}`)}><NavIcon name={area.icon} /><span>{area.label}</span></button>)}</nav><div className="sidebar-account"><span>{user.email}</span><button type="button" onClick={() => { if (confirmDiscard()) onLogout() }}>Sign out</button><span className="app-version">Version {APP_VERSION}</span></div></aside>
    <main className="dashboard-main"><header className="dashboard-header"><div><p className="eyebrow">Coach workspace</p><h1>{currentArea.label}</h1><p className="subtitle">{currentArea.subtitle}</p></div></header>
      {message && <p className="notice" role="status">{message} <button className="link-btn" onClick={() => setMessage('')}>Dismiss</button></p>}
      <div className="desktop-context">{context}</div>
      <button className="mobile-context-trigger" type="button" aria-haspopup="dialog" onClick={() => contextDialogRef.current?.showModal()}><span className="mobile-context-text"><strong>{contextPrimary}</strong><small>{contextSecondary}</small></span><span className="mobile-context-change">Change <span aria-hidden="true">⌄</span></span></button>
      <dialog ref={contextDialogRef} className="mobile-context-dialog" aria-labelledby="context-dialog-title" onClick={event => { if (event.target === event.currentTarget) event.currentTarget.close() }}><div className="context-sheet"><div className="context-sheet-heading"><div><p className="eyebrow">Current selection</p><h2 id="context-dialog-title">Team, period and player</h2></div><button type="button" aria-label="Close selection" onClick={() => contextDialogRef.current?.close()}>×</button></div>{context}<button className="context-sheet-done" type="button" onClick={() => contextDialogRef.current?.close()}>Done</button></div></dialog>
      {currentArea.id === 'settings' && selectedTeam && matrixEditorTeam === teamId && canManageTeam(selectedTeam) && <MatrixEditor key={teamId} teamId={teamId} onMessage={setMessage} onPublished={() => getPeriods(teamId).then(setPeriods).catch(e => setMessage(fail(e)))} onClose={() => { setMatrixEditorTeam(null); setMatrices(previous => Object.fromEntries(Object.entries(previous).filter(([key]) => !key.startsWith(`${teamId}:`)))) }} />}
      {currentArea.id === 'settings' && matrixEditorTeam !== teamId && <div className="settings-grid">
        <Section title="Teams" description="Choose a team or create another coaching workspace"><form className="inline-row" onSubmit={createTeamAction}><input aria-label="New team name" placeholder="New team name" required maxLength={120} value={newTeam} onChange={e => setNewTeam(e.target.value)} /><button>Add team</button></form></Section>
        {selectedTeam && <>
          <Section title="Periods" description="Organise assessments over time"><div className="settings-list">{periods.map(period => <div className="settings-item" key={period.id}><span>{period.label} {period.is_active && <span className="status-pill">Active</span>}{period.matrix_label && <small>Skill matrix: {period.matrix_label}</small>}</span><div className="item-actions">{!period.is_active && <button type="button" onClick={async () => { try { await activatePeriod(teamId, period.id); setPeriods(previous => previous.map(p => ({ ...p, is_active: p.id === period.id }))); setMessage('Active period updated.') } catch (e) { setMessage(fail(e)) } }}>Set active</button>}<button type="button" onClick={() => renamePeriodAction(period)}>Rename</button>{canManageTeam(selectedTeam) && <button type="button" onClick={() => deletePeriodAction(period)}>Delete</button>}</div></div>)}</div><form className="inline-row" onSubmit={createPeriodAction}><input aria-label="New period label" placeholder="New period label" required maxLength={100} value={newPeriod} onChange={e => setNewPeriod(e.target.value)} /><button>Add period</button></form></Section>
          <Section title="Squad" description="Players remain in your records after archiving"><div className="settings-list">{players.map(player => <div className="settings-item" key={player.id}><span>{player.name} {!player.active && <span className="status-pill muted-pill">Archived</span>}</span><div className="item-actions"><button type="button" onClick={async () => { const name = window.prompt('New player name', player.name); if (!name?.trim()) return; try { const updated = await renamePlayer(teamId, player.id, name.trim()); setPlayers(previous => previous.map(p => p.id === updated.id ? updated : p)) } catch (e) { setMessage(fail(e)) } }}>Rename</button>{player.active ? <button type="button" onClick={async () => { if (!window.confirm(`Archive ${player.name}? Assessment history stays available.`)) return; try { const updated = await archivePlayer(teamId, player.id); setPlayers(previous => previous.map(p => p.id === updated.id ? updated : p)) } catch (e) { setMessage(fail(e)) } }}>Archive</button> : <button type="button" onClick={() => restorePlayerAction(player)}>Restore</button>}</div></div>)}</div><form className="inline-row" onSubmit={createPlayerAction}><input aria-label="New player name" placeholder="New player name" required maxLength={100} value={newPlayer} onChange={e => setNewPlayer(e.target.value)} /><button>Add player</button></form></Section>
          {selectedTeam.self_assessment_enabled && selectedPeriod && <Section title="Player self-assessment" description={`Links for ${selectedPeriod.label}. Each link works once and expires after 7 days.`}><SelfAssessmentBoard key={`${teamId}-${periodId}`} teamId={teamId} period={selectedPeriod} rosterKey={players.filter(p => p.active).map(p => `${p.id}:${p.name}`).join(',')} onMessage={setMessage} /></Section>}
          {canManageTeam(selectedTeam) && <Section title="Skill matrix" description="The skills and level descriptions this team is rated on"><MatrixSummary key={teamId} teamId={teamId} onEdit={() => setMatrixEditorTeam(teamId)} /></Section>}
          {canManageTeam(selectedTeam) && <Section title="Team access" description="Only team owners can change these settings"><div className="settings-item"><span><strong>{selectedTeam.name}</strong><small>Team name</small></span><button type="button" onClick={async () => { const name = window.prompt('Team name', selectedTeam.name); if (!name?.trim()) return; try { const updated = await updateTeam(teamId, { name: name.trim(), self_assessment_enabled: selectedTeam.self_assessment_enabled }); setTeams(previous => previous.map(t => t.id === updated.id ? updated : t)) } catch (e) { setMessage(fail(e)) } }}>Rename</button></div><label className="field team-gender">Players<select value={selectedTeam.player_gender ?? 'mixed'} onChange={async e => { try { const updated = await updateTeam(teamId, { name: selectedTeam.name, self_assessment_enabled: selectedTeam.self_assessment_enabled, player_gender: e.target.value }); setTeams(previous => previous.map(t => t.id === updated.id ? updated : t)); setMatrices(previous => Object.fromEntries(Object.entries(previous).filter(([key]) => !key.startsWith(`${teamId}:`)))); setMessage('Skill descriptions now use the new wording.') } catch (error) { setMessage(fail(error)) } }}>{PLAYER_GENDERS.map(([id, label]) => <option key={id} value={id}>{label}</option>)}</select><small>Sets the pronouns used in skill descriptions</small></label><label className="checkbox"><input type="checkbox" checked={selectedTeam.self_assessment_enabled} onChange={async e => { try { const updated = await updateTeam(teamId, { name: selectedTeam.name, self_assessment_enabled: e.target.checked }); setTeams(previous => previous.map(t => t.id === updated.id ? updated : t)) } catch (error) { setMessage(fail(error)) } }} /> Allow player self-assessment</label><form className="inline-row" onSubmit={async e => { e.preventDefault(); try { const result = await inviteCoach(teamId, inviteEmail); setInviteEmail(''); setMessage(result.message) } catch (error) { setMessage(fail(error)) } }}><input type="email" aria-label="Coach email" placeholder="Coach email" required value={inviteEmail} onChange={e => setInviteEmail(e.target.value)} /><button>Invite coach</button></form><div className="members"><h3>Members</h3>{members.map(member => { const self = member.email === user.email; const soleOwner = member.role === 'owner' && members.filter(m => m.role === 'owner').length === 1; return <div className="settings-item" key={member.user_id}><span>{member.email}{self && ' (you)'} <span className="status-pill muted-pill">{member.role}</span>{soleOwner && <small>Make another member an owner before stepping down or leaving</small>}</span>{!soleOwner && <div className="item-actions"><button type="button" onClick={() => changeRoleAction(member, member.role === 'owner' ? 'coach' : 'owner')}>{member.role === 'coach' ? 'Make owner' : self ? 'Step down' : 'Make coach'}</button><button type="button" onClick={() => removeMemberAction(member)}>{self ? 'Leave' : 'Remove'}</button></div>}</div> })}</div><details key={teamId} className="audit-log" onToggle={event => { if (event.currentTarget.open) getAuditLog(teamId).then(setAuditEvents).catch(e => setMessage(fail(e))) }}><summary>Activity</summary>{auditEvents === null ? <p className="muted">Loading…</p> : auditEvents.length === 0 ? <p className="muted">No activity recorded yet.</p> : <ol>{auditEvents.map(event => <li key={event.id}><span>{auditText(event)}</span><small>{new Date(event.created_at).toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' })}</small></li>)}</ol>}</details><div className="danger-zone"><h3>Delete team</h3><p className="muted">Permanently deletes this team, its players, periods, assessments and priorities. This cannot be undone.</p><button type="button" className="danger-btn" onClick={deleteTeamAction}>Delete team</button></div></Section>}
          {!canManageTeam(selectedTeam) && members.some(m => m.email === user.email) && <Section title="Team membership" description={`You are a coach on ${selectedTeam.name}`}><button type="button" className="danger-btn" onClick={() => removeMemberAction(members.find(m => m.email === user.email))}>Leave team</button></Section>}
        </>}
        <Section title="Account" className="settings-account"><p className="settings-account-email">{user.email}</p><ChangePasswordForm /><button type="button" onClick={() => { if (confirmDiscard()) onLogout() }}>Sign out</button><p className="app-version">Version {APP_VERSION}</p></Section>
      </div>}
      {currentArea.id !== 'settings' && !selectedTeam && <Section title="Start with a team" description="Create your first team in Settings, then add a period and players."><button type="button" onClick={() => navigate('/app/settings')}>Open Settings</button></Section>}
      {selectedTeam && currentArea.id === 'assessment' && (!selectedPlayer || !selectedPeriod || !matrix ? <Section title="Ready to assess"><p className="muted">Add a player and period in Settings to begin.</p></Section> : <>
        <Section className="context-panel" title={`${selectedPlayer.name} · ${selectedPeriod.label}`} description={selectedPlayer.active ? 'Rate each skill, then save the coach assessment' : 'Coach assessment (read-only)'}>
          {!selectedPlayer.active && <ArchivedNotice player={selectedPlayer} onRestore={() => restorePlayerAction(selectedPlayer)} />}
          <form onSubmit={save}>
            <fieldset className="plain-fieldset" disabled={!selectedPlayer.active}><div className="toolbar"><label className="field">Primary position<select value={position} onChange={e => { if (skillSetFor(e.target.value) !== skillSetFor(position)) { setRatings({}); setNotes({}) } setPosition(e.target.value); if (secondary === e.target.value) setSecondary('') }}>{ALL_POSITIONS.map(p => <option key={p} value={p}>{POSITION_LABELS[p]}</option>)}</select></label><label className="field">Secondary position<select value={secondary} onChange={e => setSecondary(e.target.value)}><option value="">None</option>{ALL_POSITIONS.filter(p => p !== position).map(p => <option key={p} value={p}>{POSITION_LABELS[p]}</option>)}</select></label>{secondary && <label className="field">Frequency<select value={frequency} onChange={e => setFrequency(e.target.value)}>{FREQUENCIES.map(f => <option key={f.id} value={f.id}>{f.label}</option>)}</select></label>}</div><label className="field assessment-note">Overall note <small>Coach only</small><textarea rows={2} maxLength={1000} placeholder="Anything to remember about this assessment" value={assessmentNote} onChange={e => setAssessmentNote(e.target.value)} /></label></fieldset>
            <div className="desktop-assessment"><SkillForm matrix={matrix} position={skillSetFor(position)} ratings={ratings} notes={notes} onNoteChange={(id, note) => setNotes(previous => ({ ...previous, [id]: note }))} readOnly={!selectedPlayer.active} onChange={(id, score) => setRatings(previous => ({ ...previous, [id]: score }))} />{selectedPlayer.active && <button className="submit-btn">Save assessment</button>}</div>
            <MobileAssessment matrix={matrix} position={skillSetFor(position)} ratings={ratings} notes={notes} onNoteChange={(id, note) => setNotes(previous => ({ ...previous, [id]: note }))} readOnly={!selectedPlayer.active} onChange={(id, score) => setRatings(previous => ({ ...previous, [id]: score }))} />
          </form>
          <RevisionHistory matrix={matrix} revisions={revisions} />
        </Section>
        {selectedTeam.self_assessment_enabled && selectedPeriod.is_active && selectedPlayer.active && <Section title="Player self-assessment" description="Share a one-time link for this player and period"><div className="inline-row"><button type="button" onClick={makeLink}>Create link</button><button type="button" onClick={revokeLink}>Revoke link</button></div>{link && <div className="field link-field"><label>Copy this link now; it will not be shown again</label><input readOnly value={link} onFocus={e => e.target.select()} /><button type="button" onClick={() => navigator.clipboard.writeText(link)}>Copy link</button></div>}</Section>}
      </>)}
      {selectedTeam && currentArea.id === 'player-data' && (!selectedPlayer || !selectedPeriod || !matrix ? <Section title="No player data yet"><p className="muted">Add a player and period in Settings to view their data.</p></Section> : <Section className="context-panel" title={`${selectedPlayer.name} · ${selectedPeriod.label}`} description="Explore individual assessment results"><nav className="subtabs" aria-label="Player data views">{PLAYER_DATA_TABS.map(([id, label]) => <button aria-current={playerDataView === id ? 'page' : undefined} className={playerDataView === id ? 'active' : ''} key={id} type="button" onClick={() => { if (id !== playerDataView && confirmDiscard()) setPlayerDataView(id) }}>{label}</button>)}</nav>{playerDataView === 'summary' && <SummaryView matrix={matrix} coach={comparison?.coach} player={comparison?.player} />}{playerDataView === 'comparison' && <ComparisonView matrix={matrix} coach={comparison?.coach} player={comparison?.player} />}{playerDataView === 'progress' && <ProgressView matrix={matrix} history={history} />}{playerDataView === 'priorities' && <ConfirmedPrioritiesPanel key={`${teamId}-${playerId}`} matrix={matrix} teamId={teamId} playerId={playerId} periodId={periodId} periods={periods} />}{playerDataView === 'report' && <ReportPanel key={`${teamId}-${playerId}-${periodId}`} matrix={matrix} teamId={teamId} playerId={playerId} periodId={periodId} readOnly={!selectedPlayer.active} onMessage={setMessage} onDirtyChange={setReportDirty} />}</Section>)}
      {selectedTeam && currentArea.id === 'team-data' && (!selectedPeriod || !matrix ? <Section title="No team data yet"><p className="muted">Add a period in Settings to view team data.</p></Section> : <Section className="context-panel" title={`${selectedTeam.name} · ${selectedPeriod.label}`} description="Compare assessed skills across the squad"><HeatmapView matrix={matrix} assessments={heatmap} /></Section>)}
      {selectedTeam && currentArea.id === 'development' && (!selectedPlayer || !selectedPeriod || !matrix ? <Section title="No priorities yet"><p className="muted">Add a player and period in Settings to start.</p></Section> : <Section className="context-panel" title={`${selectedPlayer.name} · ${selectedPeriod.label}`} description={selectedPlayer.active ? 'Review and confirm the three most important priorities' : 'Priorities (read-only)'}>{!selectedPlayer.active && <ArchivedNotice player={selectedPlayer} onRestore={() => restorePlayerAction(selectedPlayer)} />}<PrioritiesView matrix={matrix} coach={comparison?.coach} player={comparison?.player} teamId={teamId} playerId={playerId} periodId={periodId} followUp={priorityFollowUp(periods, history, periodId, comparison?.coach)} onDirtyChange={setPrioritiesDirty} readOnly={!selectedPlayer.active} /></Section>)}
    </main>
    <nav className="bottom-nav" aria-label="Main navigation">{AREAS.map(area => <button key={area.id} type="button" className={area.id === currentArea.id ? 'active' : ''} aria-current={area.id === currentArea.id ? 'page' : undefined} aria-label={area.label} onClick={() => navigate(`/app/${area.id}`)}><NavIcon name={area.icon} /><span>{area.short}</span></button>)}</nav>
  </div>
}
