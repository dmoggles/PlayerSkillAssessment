import { useState } from 'react'
import { errorMessage, issueSelfLink, revokeSelfLink } from '../api'
import MobileAssessment from '../MobileAssessment'
import RevisionHistory from '../RevisionHistory'
import SkillForm from '../SkillForm'
import { ALL_POSITIONS, FREQUENCIES, POSITION_LABELS, skillSetFor } from '../matrix'
import { ArchivedNotice, Section } from './DashboardParts'

// Assessment: the coach rates the player for the period. The form state lives in the dashboard (it guards
// unsaved changes across areas); this renders it, plus the self-assessment link for the player.
export default function AssessmentArea({ team, player, period, matrix, form, revisions, onSave, onRestorePlayer, onMessage }) {
  const readOnly = !player.active
  const { position, secondary, frequency, ratings, notes, note, carried } = form
  const changePosition = value => {
    if (skillSetFor(value) !== skillSetFor(position)) { form.setRatings({}); form.setNotes({}) }
    form.setPosition(value)
    if (secondary === value) form.setSecondary('')
  }
  const setNote = (id, text) => form.setNotes(previous => ({ ...previous, [id]: text }))
  return <>
    <Section className="context-panel" title={`${player.name} · ${period.label}`} description={readOnly ? 'Coach assessment (read-only)' : 'Rate each skill, then save the coach assessment'}>
      {readOnly && <ArchivedNotice player={player} onRestore={onRestorePlayer} />}
      <form onSubmit={onSave}>
        <fieldset className="plain-fieldset" disabled={readOnly}>
          <div className="toolbar">
            <label className="field">Primary position<select value={position} onChange={e => changePosition(e.target.value)}>
              {ALL_POSITIONS.map(p => <option key={p} value={p}>{POSITION_LABELS[p]}</option>)}
            </select></label>
            <label className="field">Secondary position<select value={secondary} onChange={e => form.setSecondary(e.target.value)}>
              <option value="">None</option>{ALL_POSITIONS.filter(p => p !== position).map(p => <option key={p} value={p}>{POSITION_LABELS[p]}</option>)}
            </select></label>
            {secondary && <label className="field">Frequency<select value={frequency} onChange={e => form.setFrequency(e.target.value)}>
              {FREQUENCIES.map(f => <option key={f.id} value={f.id}>{f.label}</option>)}
            </select></label>}
          </div>
          <label className="field assessment-note">Overall note <small>Coach only</small>
            <textarea rows={2} maxLength={1000} placeholder="Anything to remember about this assessment" value={note} onChange={e => form.setNote(e.target.value)} />
          </label>
        </fieldset>
        {carried.length > 0 && <div className="carried-banner" role="status">
          <span><strong>{carried.length} {carried.length === 1 ? 'rating is' : 'ratings are'} carried from last period.</strong> Review each one: change it, or press Keep if it still holds. Carried ratings stay marked until then.</span>
          {!readOnly && <button type="button" onClick={() => form.setCarried([])}>Mark all as reviewed</button>}
        </div>}
        <div className="desktop-assessment">
          <SkillForm matrix={matrix} position={skillSetFor(position)} ratings={ratings} notes={notes} onNoteChange={setNote} readOnly={readOnly} onChange={form.rate} carried={carried} onKeepCarried={form.keepCarried} />
          {!readOnly && <button className="submit-btn">Save assessment</button>}
        </div>
        <MobileAssessment matrix={matrix} position={skillSetFor(position)} ratings={ratings} notes={notes} onNoteChange={setNote} readOnly={readOnly} onChange={form.rate} carried={carried} onKeepCarried={form.keepCarried} />
      </form>
      <RevisionHistory matrix={matrix} revisions={revisions} />
    </Section>
    {team.self_assessment_enabled && period.is_active && !readOnly && <SelfLinkSection key={`${player.id}-${period.id}`} teamId={team.id} playerId={player.id} periodId={period.id} onMessage={onMessage} />}
  </>
}

// A one-time self-assessment link for this player and period; the link is shown only once.
function SelfLinkSection({ teamId, playerId, periodId, onMessage }) {
  const [link, setLink] = useState('')
  const make = async () => {
    try { const value = await issueSelfLink(teamId, playerId, periodId); setLink(value.url); onMessage('New link created. Copy it now; it will not be shown again.') } catch (e) { onMessage(errorMessage(e)) }
  }
  const revoke = async () => {
    try { await revokeSelfLink(teamId, playerId, periodId); setLink(''); onMessage('Link revoked.') } catch (e) { onMessage(errorMessage(e)) }
  }
  return <Section title="Player self-assessment" description="Share a one-time link for this player and period">
    <div className="inline-row"><button type="button" onClick={make}>Create link</button><button type="button" onClick={revoke}>Revoke link</button></div>
    {link && <div className="field link-field">
      <label>Copy this link now; it will not be shown again</label>
      <input readOnly value={link} onFocus={e => e.target.select()} />
      <button type="button" onClick={() => navigator.clipboard.writeText(link)}>Copy link</button>
    </div>}
  </Section>
}
