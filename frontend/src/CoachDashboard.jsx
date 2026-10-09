import { useCallback, useEffect, useRef, useState } from 'react'
import { useBlocker, useLocation, useNavigate } from 'react-router-dom'
import { errorMessage, getCoachAssessment, getComparison, getMembers, getMatrixVersion, getPeriodAssessments, getPeriodGroups, getPeriods,
  getPlayerHistory, getPlayers, getRevisions, getTeams, restorePlayer, submitCoachAssessment } from './api'
import AssessmentArea from './areas/AssessmentArea'
import { NavIcon, Section } from './areas/DashboardParts'
import DevelopmentArea from './areas/DevelopmentArea'
import PlayerDataArea from './areas/PlayerDataArea'
import SettingsArea from './areas/SettingsArea'
import TeamDataArea from './areas/TeamDataArea'
import { sectionsFor, skillSetFor } from './matrix'
import { APP_VERSION } from './version'
import { AREAS, assessmentSignature, formFromAssessment, formSignature, initialPeriodId, initialPlayerId, previousCoachAssessment } from './dashboardModel'

const fail = errorMessage

// The coach workspace: navigation, the team / period / player selection, the data each area shares, and the guard
// against leaving unsaved changes. Each area renders itself from areas/.
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
  const [teamDataView, setTeamDataView] = useState('heatmap')
  const [teamDataPosition, setTeamDataPosition] = useState('')
  // The chosen playing group for Team data: null follows the default (the largest group), 'all' shows everyone.
  const [teamDataGroup, setTeamDataGroup] = useState(null)
  // Skills whose score was carried from last period and not yet reviewed (see formFromAssessment).
  const [carried, setCarried] = useState([])
  // Playing groups in the selected period: player id -> U-number.
  const [groups, setGroups] = useState({})
  const [members, setMembers] = useState([])
  const [message, setMessage] = useState('')
  const [position, setPosition] = useState('defender')
  const [secondary, setSecondary] = useState('')
  const [frequency, setFrequency] = useState('sometimes')
  const [ratings, setRatings] = useState({})
  const [notes, setNotes] = useState({})
  const [previousCoach, setPreviousCoach] = useState(null)
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
  const assessmentDirty = assessmentBaseline !== null && assessmentSignature(position, secondary, frequency, ratings, notes, assessmentNote, carried) !== assessmentBaseline
  const dirty = assessmentDirty || prioritiesDirty || reportDirty
  const blocker = useBlocker(dirty)
  const blockerPrompted = useRef(false)
  const contextDialogRef = useRef(null)

  const applyForm = useCallback((assessment, previous = null) => {
    const form = formFromAssessment(assessment, previous)
    setPosition(form.position); setSecondary(form.secondary); setFrequency(form.frequency)
    setRatings(form.ratings); setNotes(form.notes); setAssessmentNote(form.note); setCarried(form.carried)
    setAssessmentBaseline(formSignature(form))
  }, [])
  const restoreAssessment = useCallback(() => applyForm(coach, previousCoach), [applyForm, coach, previousCoach])
  // Changing a carried score makes it a fresh rating; Keep confirms a carried one is still right.
  const rate = (id, score) => { setRatings(previous => ({ ...previous, [id]: score })); setCarried(previous => previous.filter(skill => skill !== id)) }
  const keepCarried = id => setCarried(previous => previous.filter(skill => skill !== id))
  // Read inside the assessment-loading effect without re-running it (and discarding edits) whenever periods change.
  const periodsRef = useRef(periods)
  useEffect(() => { periodsRef.current = periods }, [periods])

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
    if (id !== teamId && confirmDiscard()) selectTeam(id)
  }
  function selectTeam(id) {
    setTeamId(id); setPlayers([]); setPeriods([]); setPlayerId(''); setPeriodId('')
    setCoach(null); setComparison(null); setHistory([]); setRevisions([]); setHeatmap([]); setAssessmentBaseline(null)
  }
  function choosePlayer(id) {
    if (!confirmDiscard()) return
    setPlayerId(id); setCoach(null); setComparison(null); setHistory([]); setRevisions([]); setRatings({}); setNotes({}); setAssessmentNote(''); setAssessmentBaseline(null)
  }
  function choosePeriod(id) {
    if (confirmDiscard()) selectPeriod(id)
  }
  function selectPeriod(id) {
    setPeriodId(id); setCoach(null); setComparison(null); setHistory([]); setRevisions([]); setHeatmap([]); setRatings({}); setNotes({}); setAssessmentNote(''); setAssessmentBaseline(null)
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
    if (!teamId || !periodId) return
    let live = true
    getPeriodGroups(teamId, periodId).then(value => { if (live) setGroups(value) }).catch(() => { if (live) setGroups({}) })
    return () => { live = false }
  }, [teamId, periodId])

  useEffect(() => {
    if (!teamId || !playerId || !periodId) return
    let live = true
    Promise.allSettled([getCoachAssessment(teamId, playerId, periodId), getComparison(teamId, playerId, periodId), getPlayerHistory(teamId, playerId)]).then(([assessmentResult, comparisonResult, historyResult]) => {
      if (!live) return
      if (comparisonResult.status === 'fulfilled') setComparison(comparisonResult.value)
      if (historyResult.status === 'fulfilled') setHistory(historyResult.value)
      if (assessmentResult.status !== 'fulfilled') { setMessage(fail(assessmentResult.reason)); return }
      const assessment = assessmentResult.value
      const previous = historyResult.status === 'fulfilled' ? previousCoachAssessment(historyResult.value, periodsRef.current, periodId) : null
      setCoach(assessment); setPreviousCoach(previous)
      applyForm(assessment, previous)
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

  async function save(event) {
    event.preventDefault()
    const skills = sectionsFor(matrix, skillSetFor(position)).flatMap(section => section.skills)
    try {
      const assessment = await submitCoachAssessment(teamId, {
        player_id: Number(playerId), period_id: Number(periodId), version: coach?.version ?? 0,
        primary_position: position, secondary_position: secondary || null,
        secondary_position_frequency: secondary ? frequency : null,
        note: assessmentNote.trim() || null,
        ratings: skills.map(skill => ({ skill_id: skill.id, score: ratings[skill.id] ?? null, note: notes[skill.id]?.trim() || null, carried: carried.includes(skill.id) })),
      })
      setCoach(assessment); setMessage(assessment.unchanged ? 'No changes to save.' : 'Assessment saved.')
      applyForm(assessment)
      getComparison(teamId, playerId, periodId).then(setComparison)
      getPlayerHistory(teamId, playerId).then(setHistory)
      getRevisions(teamId, assessment.id).then(setRevisions)
    } catch (e) { setMessage(fail(e)) }
  }
  async function restorePlayerAction(player) {
    try { const updated = await restorePlayer(teamId, player.id); setPlayers(previous => previous.map(p => p.id === updated.id ? updated : p)); setMessage(`${updated.name} restored to the squad.`) } catch (e) { setMessage(fail(e)) }
  }
  // Drop cached matrix documents for a team, after its matrix or its player wording changes.
  function forgetMatrices(id) {
    setMatrices(previous => Object.fromEntries(Object.entries(previous).filter(([key]) => !key.startsWith(`${id}:`))))
  }
  function dropTeam(id) {
    const remaining = teams.filter(t => t.id !== Number(id))
    setTeams(remaining)
    setMembers([])
    selectTeam(remaining.length ? String(remaining[0].id) : '')
  }
  const context = <div className="context-controls">
    <label className="field">Team<select value={teamId} onChange={event => chooseTeam(event.target.value)}><option value="">Select team</option>{teams.map(team => <option key={team.id} value={team.id}>{team.name}</option>)}</select></label>
    {selectedTeam && <label className="field">Period<select value={periodId} onChange={event => choosePeriod(event.target.value)}><option value="">Select period</option>{periods.map(period => <option key={period.id} value={period.id}>{period.label}{period.is_active ? ' · active' : ''}</option>)}</select></label>}
    {selectedTeam && ['assessment', 'player-data', 'development'].includes(currentArea.id) && <label className="field">Player<select value={playerId} onChange={event => choosePlayer(event.target.value)}><option value="">Select player</option>{players.map(player => <option key={player.id} value={player.id}>{player.name}{player.active ? '' : ' · archived'}</option>)}</select></label>}
  </div>
  const needsPlayer = ['assessment', 'player-data', 'development'].includes(currentArea.id)
  // With self-assessment off, nothing derived from self-ratings is shown: no Comparison tab, no player columns or
  // disagreements, and priorities are scored on the coach's ratings alone. (The API hides them too.)
  const selfAssessmentOn = Boolean(selectedTeam?.self_assessment_enabled)
  const selfAssessment = selfAssessmentOn ? comparison?.player ?? null : null
  const contextPrimary = needsPlayer && selectedPlayer ? selectedPlayer.name : selectedTeam?.name ?? 'Choose a team'
  const contextSecondary = [needsPlayer && selectedPlayer ? selectedTeam?.name : null, selectedPeriod?.label].filter(Boolean).join(' · ') || 'Tap to choose team and period'

  return <div className="dashboard-shell">
    <aside className="dashboard-sidebar"><div className="brand"><span className="brand-mark">PS</span><div><strong>Player Skills</strong><span>Coach workspace</span></div></div><nav aria-label="Main navigation" className="side-nav">{AREAS.map(area => <button key={area.id} type="button" className={area.id === currentArea.id ? 'active' : ''} aria-current={area.id === currentArea.id ? 'page' : undefined} onClick={() => navigate(`/app/${area.id}`)}><NavIcon name={area.icon} /><span>{area.label}</span></button>)}</nav><div className="sidebar-account"><span>{user.email}</span><button type="button" onClick={() => { if (confirmDiscard()) onLogout() }}>Sign out</button><span className="app-version">Version {APP_VERSION}</span></div></aside>
    <main className="dashboard-main"><header className="dashboard-header"><div><p className="eyebrow">Coach workspace</p><h1>{currentArea.label}</h1><p className="subtitle">{currentArea.subtitle}</p></div></header>
      {message && <p className="notice" role="status">{message} <button className="link-btn" onClick={() => setMessage('')}>Dismiss</button></p>}
      <div className="desktop-context">{context}</div>
      <button className="mobile-context-trigger" type="button" aria-haspopup="dialog" onClick={() => contextDialogRef.current?.showModal()}><span className="mobile-context-text"><strong>{contextPrimary}</strong><small>{contextSecondary}</small></span><span className="mobile-context-change">Change <span aria-hidden="true">⌄</span></span></button>
      <dialog ref={contextDialogRef} className="mobile-context-dialog" aria-labelledby="context-dialog-title" onClick={event => { if (event.target === event.currentTarget) event.currentTarget.close() }}><div className="context-sheet"><div className="context-sheet-heading"><div><p className="eyebrow">Current selection</p><h2 id="context-dialog-title">Team, period and player</h2></div><button type="button" aria-label="Close selection" onClick={() => contextDialogRef.current?.close()}>×</button></div>{context}<button className="context-sheet-done" type="button" onClick={() => contextDialogRef.current?.close()}>Done</button></div></dialog>
      {currentArea.id === 'settings' && <SettingsArea key={teamId} user={user} onLogout={onLogout} dashboard={{
        team: selectedTeam, teams, setTeams, players, setPlayers, periods, setPeriods, period: selectedPeriod, groups, setGroups, members, setMembers,
        chooseTeam, choosePeriod, choosePlayer, selectPeriod, dropTeam, confirmDiscard, restorePlayer: restorePlayerAction, forgetMatrices, onMessage: setMessage,
      }} />}
      {currentArea.id !== 'settings' && !selectedTeam && <Section title="Start with a team" description="Create your first team in Settings, then add a period and players."><button type="button" onClick={() => navigate('/app/settings')}>Open Settings</button></Section>}
      {selectedTeam && currentArea.id === 'assessment' && (!selectedPlayer || !selectedPeriod || !matrix
        ? <Section title="Ready to assess"><p className="muted">Add a player and period in Settings to begin.</p></Section>
        : <AssessmentArea team={selectedTeam} player={selectedPlayer} period={selectedPeriod} matrix={matrix} revisions={revisions} onSave={save}
          onRestorePlayer={() => restorePlayerAction(selectedPlayer)} onMessage={setMessage}
          form={{ position, setPosition, secondary, setSecondary, frequency, setFrequency, ratings, setRatings, notes, setNotes,
            note: assessmentNote, setNote: setAssessmentNote, carried, setCarried, rate, keepCarried }} />)}
      {selectedTeam && currentArea.id === 'player-data' && (!selectedPlayer || !selectedPeriod || !matrix
        ? <Section title="No player data yet"><p className="muted">Add a player and period in Settings to view their data.</p></Section>
        : <PlayerDataArea team={selectedTeam} player={selectedPlayer} period={selectedPeriod} periods={periods} matrix={matrix} comparison={comparison}
          selfAssessment={selfAssessment} history={history} view={playerDataView} onViewChange={setPlayerDataView} confirmDiscard={confirmDiscard}
          onMessage={setMessage} onReportDirty={setReportDirty} />)}
      {selectedTeam && currentArea.id === 'team-data' && (!selectedPeriod || !matrix
        ? <Section title="No team data yet"><p className="muted">Add a period in Settings to view team data.</p></Section>
        : <TeamDataArea team={selectedTeam} period={selectedPeriod} matrix={matrix} players={players} groups={groups} heatmap={heatmap}
          view={teamDataView} onViewChange={setTeamDataView} position={teamDataPosition} onPositionChange={setTeamDataPosition}
          groupChoice={teamDataGroup} onGroupChoice={setTeamDataGroup} onMessage={setMessage} />)}
      {selectedTeam && currentArea.id === 'development' && (!selectedPlayer || !selectedPeriod || !matrix
        ? <Section title="No priorities yet"><p className="muted">Add a player and period in Settings to start.</p></Section>
        : <DevelopmentArea teamId={teamId} player={selectedPlayer} period={selectedPeriod} periods={periods} matrix={matrix} comparison={comparison}
          selfAssessment={selfAssessment} history={history} onPrioritiesDirty={setPrioritiesDirty} onRestorePlayer={() => restorePlayerAction(selectedPlayer)} />)}
    </main>
    <nav className="bottom-nav" aria-label="Main navigation">{AREAS.map(area => <button key={area.id} type="button" className={area.id === currentArea.id ? 'active' : ''} aria-current={area.id === currentArea.id ? 'page' : undefined} aria-label={area.label} onClick={() => navigate(`/app/${area.id}`)}><NavIcon name={area.icon} /><span>{area.short}</span></button>)}</nav>
  </div>
}
