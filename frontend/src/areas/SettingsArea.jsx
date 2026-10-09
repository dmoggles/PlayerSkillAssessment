import { lazy, Suspense, useState } from 'react'
import { activatePeriod, addPlayer, archivePlayer, createTeam, deletePeriod, deleteTeam, errorMessage, getAuditLog, getPeriods, inviteCoach,
  removeMember, renamePeriod, renamePlayer, setMemberRole, setPlayerGroup, updateTeam } from '../api'
import ChangePasswordForm from '../ChangePasswordForm'
import DrillLibrary, { DrillLibrarySummary } from '../DrillLibrary'
import MatrixSummary from '../MatrixSummary'
import PeriodForm from '../PeriodForm'
import SelfAssessmentBoard from '../SelfAssessmentBoard'
import { auditText } from '../auditModel'

const MatrixEditor = lazy(() => import('../MatrixEditor'))
import { AGE_GROUPS, PLAYER_GENDERS, canManageTeam, initialPeriodId, squadGroups } from '../dashboardModel'
import { APP_VERSION } from '../version'
import { Section } from './DashboardParts'

const fail = errorMessage

// Settings: teams, periods, the squad, self-assessment links, the drill library, the skill matrix, team access and
// the account. `dashboard` carries the shared state and the dashboard actions that settings changes go through.
export default function SettingsArea({ user, dashboard, onLogout }) {
  const { team, setTeams, players, setPlayers, periods, setPeriods, period, groups, setGroups, members, setMembers,
    chooseTeam, choosePeriod, choosePlayer, selectPeriod, dropTeam, confirmDiscard, restorePlayer, forgetMatrices, onMessage } = dashboard
  const [drillLibraryOpen, setDrillLibraryOpen] = useState(false)
  const [editingMatrix, setEditingMatrix] = useState(false)
  const owner = canManageTeam(team)
  const squad = squadGroups(players, groups)

  if (team && editingMatrix && owner) {
    return <Suspense fallback={<p className="muted" role="status">Loading skill matrix…</p>}>
      <MatrixEditor key={team.id} teamId={String(team.id)} onMessage={onMessage}
        onPublished={() => getPeriods(team.id).then(setPeriods).catch(e => onMessage(fail(e)))}
        onClose={() => { setEditingMatrix(false); forgetMatrices(team.id) }} />
    </Suspense>
  }
  if (drillLibraryOpen) {
    return <Section title="Drill library" description="Drills tagged to skills, each with easier and harder variations">
      <button type="button" className="link-btn back-link" onClick={() => setDrillLibraryOpen(false)}>← Back to settings</button>
      <DrillLibrary key={`${team?.id}-${period?.id}-${squad.single}`} ageGroup={squad.single} ageSpan={squad.span} onMessage={onMessage} />
    </Section>
  }
  return <div className="settings-grid">
    <TeamsSection onCreated={created => { setTeams(previous => [...previous, created]); chooseTeam(String(created.id)); onMessage('Team created.') }} onMessage={onMessage} />
    {team && <>
      <PeriodsSection team={team} periods={periods} setPeriods={setPeriods} players={players} selectedPeriodId={period?.id}
        choosePeriod={choosePeriod} selectPeriod={selectPeriod} confirmDiscard={confirmDiscard} onMessage={onMessage} />
      <SquadSection team={team} period={period} players={players} setPlayers={setPlayers} groups={groups} setGroups={setGroups}
        choosePlayer={choosePlayer} restorePlayer={restorePlayer} onMessage={onMessage} />
      {team.self_assessment_enabled && period && <Section title="Player self-assessment" description={`Links for ${period.label}. Each link works once and expires after 7 days.`}>
        <SelfAssessmentBoard key={`${team.id}-${period.id}`} teamId={String(team.id)} period={period} rosterKey={players.filter(p => p.active).map(p => `${p.id}:${p.name}`).join(',')} onMessage={onMessage} />
      </Section>}
      <Section title="Drill library" description="The shared library of drills for every skill"><DrillLibrarySummary onOpen={() => setDrillLibraryOpen(true)} /></Section>
      {owner && <Section title="Skill matrix" description="The skills and level descriptions this team is rated on">
        <MatrixSummary key={team.id} teamId={String(team.id)} onEdit={() => setEditingMatrix(true)} />
      </Section>}
      {owner && <TeamAccessSection user={user} team={team} setTeams={setTeams} members={members} setMembers={setMembers} dropTeam={dropTeam}
        confirmDiscard={confirmDiscard} forgetMatrices={forgetMatrices} onMessage={onMessage} />}
      {!owner && members.some(m => m.email === user.email) && <Section title="Team membership" description={`You are a coach on ${team.name}`}>
        <MemberActions user={user} team={team} members={members} setMembers={setMembers} dropTeam={dropTeam} confirmDiscard={confirmDiscard} onMessage={onMessage} leaveOnly />
      </Section>}
    </>}
    <Section title="Account" className="settings-account">
      <p className="settings-account-email">{user.email}</p>
      <ChangePasswordForm />
      <button type="button" onClick={() => { if (confirmDiscard()) onLogout() }}>Sign out</button>
      <p className="app-version">Version {APP_VERSION}</p>
    </Section>
  </div>
}

function TeamsSection({ onCreated, onMessage }) {
  const [name, setName] = useState('')
  const submit = async event => {
    event.preventDefault()
    try { onCreated(await createTeam(name.trim())); setName('') } catch (e) { onMessage(fail(e)) }
  }
  return <Section title="Teams" description="Choose a team or create another coaching workspace">
    <form className="inline-row" onSubmit={submit}>
      <input aria-label="New team name" placeholder="New team name" required maxLength={120} value={name} onChange={e => setName(e.target.value)} />
      <button>Add team</button>
    </form>
  </Section>
}

function PeriodsSection({ team, periods, setPeriods, players, selectedPeriodId, choosePeriod, selectPeriod, confirmDiscard, onMessage }) {
  const teamId = team.id
  const activate = async period => {
    try { await activatePeriod(teamId, period.id); setPeriods(previous => previous.map(p => ({ ...p, is_active: p.id === period.id }))); onMessage('Active period updated.') } catch (e) { onMessage(fail(e)) }
  }
  const rename = async period => {
    const label = window.prompt('New period label', period.label)
    if (!label?.trim() || label.trim() === period.label) return
    try { const updated = await renamePeriod(teamId, period.id, label.trim()); setPeriods(previous => previous.map(p => p.id === updated.id ? updated : p)) } catch (e) { onMessage(fail(e)) }
  }
  const remove = async period => {
    const selected = selectedPeriodId === period.id
    if (!window.confirm(`Delete ${period.label}? Every coach assessment, self-assessment and priority recorded in this period is permanently deleted.`)) return
    if (selected && !confirmDiscard()) return
    try {
      await deletePeriod(teamId, period.id)
      const rounds = await getPeriods(teamId)
      setPeriods(rounds)
      if (selected) selectPeriod(initialPeriodId(rounds))
      onMessage('Period deleted.')
    } catch (e) { onMessage(fail(e)) }
  }
  return <Section title="Periods" description="Organise assessments over time">
    <div className="settings-list">{periods.map(period => <div className="settings-item" key={period.id}>
      <span>{period.label} {period.is_active && <span className="status-pill">Active</span>}{period.matrix_label && <small>Skill matrix: {period.matrix_label}</small>}</span>
      <div className="item-actions">
        {!period.is_active && <button type="button" onClick={() => activate(period)}>Set active</button>}
        <button type="button" onClick={() => rename(period)}>Rename</button>
        {canManageTeam(team) && <button type="button" onClick={() => remove(period)}>Delete</button>}
      </div>
    </div>)}</div>
    <PeriodForm teamId={String(teamId)} players={players} latestPeriod={periods[0] ?? null} onMessage={onMessage}
      onCreated={period => { setPeriods(previous => [period, ...previous.map(p => ({ ...p, is_active: false }))]); choosePeriod(String(period.id)); onMessage('Period created.') }} />
  </Section>
}

function SquadSection({ team, period, players, setPlayers, groups, setGroups, choosePlayer, restorePlayer, onMessage }) {
  const [name, setName] = useState('')
  const teamId = team.id
  const replace = updated => setPlayers(previous => previous.map(p => p.id === updated.id ? updated : p))
  const add = async event => {
    event.preventDefault()
    try { const player = await addPlayer(teamId, name.trim()); setPlayers(previous => [...previous, player]); choosePlayer(String(player.id)); setName(''); onMessage('Player added.') } catch (e) { onMessage(fail(e)) }
  }
  const rename = async player => {
    const value = window.prompt('New player name', player.name)
    if (!value?.trim()) return
    try { replace(await renamePlayer(teamId, player.id, value.trim())) } catch (e) { onMessage(fail(e)) }
  }
  const archive = async player => {
    if (!window.confirm(`Archive ${player.name}? Assessment history stays available.`)) return
    try { replace(await archivePlayer(teamId, player.id)) } catch (e) { onMessage(fail(e)) }
  }
  const setGroup = async (player, value) => {
    const age = value ? Number(value) : null
    try {
      await setPlayerGroup(teamId, player.id, period.id, age)
      setGroups(previous => { const next = { ...previous }; if (age) next[player.id] = age; else delete next[player.id]; return next })
    } catch (e) { onMessage(fail(e)) }
  }
  return <Section title="Squad" description={period ? `Playing groups are for ${period.label}; players remain in your records after archiving` : 'Players remain in your records after archiving'}>
    <div className="settings-list">{players.map(player => <div className="settings-item" key={player.id}>
      <span>{player.name} {!player.active && <span className="status-pill muted-pill">Archived</span>}</span>
      <div className="item-actions">
        {period && <select className="group-select" aria-label={`${player.name}'s playing group in ${period.label}`} value={groups[player.id] ?? ''} onChange={e => setGroup(player, e.target.value)}>
          <option value="">Group not set</option>{AGE_GROUPS.map(age => <option key={age} value={age}>U{age}</option>)}
        </select>}
        <button type="button" onClick={() => rename(player)}>Rename</button>
        {player.active ? <button type="button" onClick={() => archive(player)}>Archive</button> : <button type="button" onClick={() => restorePlayer(player)}>Restore</button>}
      </div>
    </div>)}</div>
    <form className="inline-row" onSubmit={add}>
      <input aria-label="New player name" placeholder="New player name" required maxLength={100} value={name} onChange={e => setName(e.target.value)} />
      <button>Add player</button>
    </form>
  </Section>
}

// Owners only: team name, player wording, self-assessment, invitations, members, the activity log and deletion.
function TeamAccessSection({ user, team, setTeams, members, setMembers, dropTeam, confirmDiscard, forgetMatrices, onMessage }) {
  const [inviteEmail, setInviteEmail] = useState('')
  const teamId = team.id
  const update = async (changes, after = () => {}) => {
    try {
      const updated = await updateTeam(teamId, { name: team.name, self_assessment_enabled: team.self_assessment_enabled, ...changes })
      setTeams(previous => previous.map(t => t.id === updated.id ? updated : t))
      after()
    } catch (e) { onMessage(fail(e)) }
  }
  const rename = () => {
    const name = window.prompt('Team name', team.name)
    if (name?.trim()) update({ name: name.trim() })
  }
  const invite = async event => {
    event.preventDefault()
    try { const result = await inviteCoach(teamId, inviteEmail); setInviteEmail(''); onMessage(result.message) } catch (e) { onMessage(fail(e)) }
  }
  const removeTeam = async () => {
    const name = window.prompt(`This permanently deletes ${team.name} with all its players, periods, assessments and priorities, and removes every member's access. Type the team name to confirm.`)
    if (name == null) return
    if (name.trim() !== team.name) { onMessage('Team name did not match. Nothing was deleted.'); return }
    if (!confirmDiscard()) return
    try { await deleteTeam(teamId, name.trim()); dropTeam(teamId); onMessage(`${team.name} deleted.`) } catch (e) { onMessage(fail(e)) }
  }
  return <Section title="Team access" description="Only team owners can change these settings">
    <div className="settings-item">
      <span><strong>{team.name}</strong><small>Team name</small></span>
      <button type="button" onClick={rename}>Rename</button>
    </div>
    <label className="field team-gender">Players
      <select value={team.player_gender ?? 'mixed'} onChange={e => update({ player_gender: e.target.value }, () => { forgetMatrices(teamId); onMessage('Skill descriptions now use the new wording.') })}>
        {PLAYER_GENDERS.map(([id, label]) => <option key={id} value={id}>{label}</option>)}
      </select>
      <small>Sets the pronouns used in skill descriptions</small>
    </label>
    <label className="checkbox"><input type="checkbox" checked={team.self_assessment_enabled} onChange={e => update({ self_assessment_enabled: e.target.checked })} /> Allow player self-assessment</label>
    <form className="inline-row" onSubmit={invite}>
      <input type="email" aria-label="Coach email" placeholder="Coach email" required value={inviteEmail} onChange={e => setInviteEmail(e.target.value)} />
      <button>Invite coach</button>
    </form>
    <MemberActions user={user} team={team} members={members} setMembers={setMembers} setTeams={setTeams} dropTeam={dropTeam} confirmDiscard={confirmDiscard} onMessage={onMessage} />
    <ActivityLog key={teamId} teamId={teamId} onMessage={onMessage} />
    <div className="danger-zone">
      <h3>Delete team</h3>
      <p className="muted">Permanently deletes this team, its players, periods, assessments and priorities. This cannot be undone.</p>
      <button type="button" className="danger-btn" onClick={removeTeam}>Delete team</button>
    </div>
  </Section>
}

// The members list with role changes and removal (owners), or just "Leave team" for a coach (leaveOnly).
function MemberActions({ user, team, members, setMembers, setTeams = () => {}, dropTeam, confirmDiscard, onMessage, leaveOnly = false }) {
  const teamId = team.id
  const changeRole = async (member, role) => {
    const self = member.email === user.email
    const question = role === 'owner'
      ? `Make ${member.email} an owner? Owners can change team settings, manage members and delete the team.`
      : self ? 'Step down to coach? You will no longer be able to manage this team.' : `Change ${member.email} to a coach?`
    if (!window.confirm(question)) return
    try {
      const updated = await setMemberRole(teamId, member.user_id, role)
      setMembers(previous => previous.map(m => m.user_id === updated.user_id ? updated : m))
      if (self) setTeams(previous => previous.map(t => t.id === teamId ? { ...t, role } : t))
    } catch (e) { onMessage(fail(e)) }
  }
  const remove = async member => {
    const self = member.email === user.email
    if (!window.confirm(self ? `Leave ${team.name}? You will lose access to it.` : `Remove ${member.email} from this team?`)) return
    if (self && !confirmDiscard()) return
    try {
      await removeMember(teamId, member.user_id)
      if (self) { dropTeam(teamId); onMessage(`You left ${team.name}.`) } else setMembers(previous => previous.filter(row => row.user_id !== member.user_id))
    } catch (e) { onMessage(fail(e)) }
  }
  if (leaveOnly) return <button type="button" className="danger-btn" onClick={() => remove(members.find(m => m.email === user.email))}>Leave team</button>
  return <div className="members"><h3>Members</h3>{members.map(member => {
    const self = member.email === user.email
    const soleOwner = member.role === 'owner' && members.filter(m => m.role === 'owner').length === 1
    return <div className="settings-item" key={member.user_id}>
      <span>{member.email}{self && ' (you)'} <span className="status-pill muted-pill">{member.role}</span>{soleOwner && <small>Make another member an owner before stepping down or leaving</small>}</span>
      {!soleOwner && <div className="item-actions">
        <button type="button" onClick={() => changeRole(member, member.role === 'owner' ? 'coach' : 'owner')}>{member.role === 'coach' ? 'Make owner' : self ? 'Step down' : 'Make coach'}</button>
        <button type="button" onClick={() => remove(member)}>{self ? 'Leave' : 'Remove'}</button>
      </div>}
    </div>
  })}</div>
}

// The team's activity log, loaded when opened.
function ActivityLog({ teamId, onMessage }) {
  const [events, setEvents] = useState(null)
  return <details className="audit-log" onToggle={event => { if (event.currentTarget.open) getAuditLog(teamId).then(setEvents).catch(e => onMessage(fail(e))) }}>
    <summary>Activity</summary>
    {events === null ? <p className="muted">Loading…</p> : events.length === 0 ? <p className="muted">No activity recorded yet.</p>
      : <ol>{events.map(event => <li key={event.id}><span>{auditText(event)}</span><small>{new Date(event.created_at).toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' })}</small></li>)}</ol>}
  </details>
}
