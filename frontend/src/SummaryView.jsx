import {
  ratingMap, sectionAverages, skillCallouts, completeness, disagreements, CONVERSATION_FRAMING,
} from './assessment'

const fmt1 = (v) => (v == null ? '—' : v.toFixed(1))

const LEVEL_LABEL = { notable: 'Notable', significant: 'Significant' }
const DIRECTION_LABEL = {
  overestimation: 'Rates self higher',
  underestimation: 'Rates self lower',
}

export default function SummaryView({ matrix, coach, player }) {
  if (!coach && !player) {
    return <p className="muted">No assessments recorded for this player yet.</p>
  }

  const position = coach?.position ?? player?.position ?? 'outfield'
  const coachMap = ratingMap(coach)
  const playerMap = ratingMap(player)

  const comp = completeness(matrix, position, coachMap)
  const sections = sectionAverages(matrix, position, coachMap, playerMap)
  const { top, bottom } = skillCallouts(matrix, position, coachMap, playerMap)

  const allFlags = disagreements(matrix, position, coachMap, playerMap)
  const flagged = allFlags
    .filter(f => f.level !== 'aligned')
    .sort((a, b) => b.abs - a.abs)
  const foundational = flagged.filter(f => f.isRoot && f.level === 'significant')

  return (
    <div className="summary">
      <div className="summary-block">
        <div className="completeness">
          <span className="completeness-label">Coach assessment complete</span>
          <div className="completeness-bar">
            <div className="completeness-fill" style={{ width: `${comp.pct}%` }} />
          </div>
          <span className="completeness-num">
            {comp.assessed}/{comp.applicable} ({Math.round(comp.pct)}%)
          </span>
        </div>
        {comp.pct < 100 && (
          <p className="muted small">Priorities can be generated once the coach assessment is 100% complete.</p>
        )}
      </div>

      <div className="summary-block">
        <h3>Section averages</h3>
        <div className="cmp-table">
          <div className="cmp-row cmp-head">
            <span className="cmp-skill">Section</span>
            <span className="cmp-cell">Coach</span>
            <span className="cmp-cell">Player</span>
            <span className="cmp-cell">Combined</span>
          </div>
          {sections.map(s => (
            <div key={s.id} className="cmp-row">
              <span className="cmp-skill">{s.label}</span>
              <span className="cmp-cell">{fmt1(s.coach)}</span>
              <span className="cmp-cell">{fmt1(s.player)}</span>
              <span className="cmp-cell"><strong>{fmt1(s.combined)}</strong></span>
            </div>
          ))}
        </div>
      </div>

      <div className="summary-cols">
        <div className="summary-block">
          <h3>Strengths</h3>
          {top.length ? (
            <ol className="callout-list">
              {top.map(x => <li key={x.skill_id}><span>{x.label}</span><span className="callout-score">{fmt1(x.score)}</span></li>)}
            </ol>
          ) : <p className="muted small">No scores yet.</p>}
        </div>
        <div className="summary-block">
          <h3>Focus areas</h3>
          {bottom.length ? (
            <ol className="callout-list">
              {bottom.map(x => <li key={x.skill_id}><span>{x.label}</span><span className="callout-score">{fmt1(x.score)}</span></li>)}
            </ol>
          ) : <p className="muted small">No scores yet.</p>}
        </div>
      </div>

      {foundational.length > 0 && (
        <div className="summary-block flags-foundational">
          <h3>⚠ Foundational disagreements</h3>
          <p className="muted small">Significant gaps on root skills — most likely to undermine the development plan.</p>
          {foundational.map(f => (
            <div key={f.skill_id} className="flag-item">
              <div className="flag-head">
                <span className="flag-skill">{f.label}</span>
                <span className="flag-tag significant">{DIRECTION_LABEL[f.direction]} ({f.diff > 0 ? '+' : ''}{f.diff})</span>
              </div>
              <p className="flag-framing">{CONVERSATION_FRAMING[f.direction]}</p>
            </div>
          ))}
        </div>
      )}

      <div className="summary-block">
        <h3>Disagreements</h3>
        {!player ? (
          <p className="muted small">The player has not submitted a self-assessment yet, so disagreements cannot be shown.</p>
        ) : !coach ? (
          <p className="muted small">No coach assessment has been saved yet, so disagreements cannot be shown.</p>
        ) : flagged.length ? (
          flagged.map(f => (
            <div key={f.skill_id} className="flag-item">
              <div className="flag-head">
                <span className="flag-skill">{f.label}</span>
                <span className={`flag-tag ${f.level}`}>
                  {LEVEL_LABEL[f.level]} · {DIRECTION_LABEL[f.direction]} ({f.diff > 0 ? '+' : ''}{f.diff})
                </span>
              </div>
            </div>
          ))
        ) : allFlags.length === 0 ? (
          <p className="muted small">No skills have been rated by both coach and player yet.</p>
        ) : (
          <p className="muted small">Coach and player are aligned on all jointly-rated skills (no gaps of 2+).</p>
        )}
      </div>
    </div>
  )
}
