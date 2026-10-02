import { sectionsFor } from './matrix'

const toMap = (assessment) => {
  const map = {}
  if (assessment) {
    for (const r of assessment.ratings) map[r.skill_id] = r.score
  }
  return map
}

export default function ComparisonView({ matrix, coach, player }) {
  // Pick the skill set from whichever assessment we have (prefer coach).
  const position = coach?.position ?? player?.position ?? 'outfield'
  const sections = sectionsFor(matrix, position)

  const coachMap = toMap(coach)
  const playerMap = toMap(player)

  if (!coach && !player) {
    return <p className="muted">No assessments recorded for this player yet.</p>
  }

  return (
    <div className="comparison">
      <div className="comparison-legend">
        <span className="legend-chip coach-chip">Coach</span>
        <span className="legend-chip player-chip">Player</span>
        <span className="muted">Δ shows coach minus player</span>
      </div>

      {!player && <p className="warning">No player self-assessment submitted yet.</p>}
      {!coach && <p className="warning">You haven't saved a coach assessment yet.</p>}

      {sections.map(section => (
        <div key={section.id} className="section">
          <h3>{section.label}</h3>
          <div className="cmp-table">
            <div className="cmp-row cmp-head">
              <span className="cmp-skill">Skill</span>
              <span className="cmp-cell">Coach</span>
              <span className="cmp-cell">Player</span>
              <span className="cmp-cell">Δ</span>
            </div>
            {section.skills.map(skill => {
              const c = coachMap[skill.id] ?? null
              const p = playerMap[skill.id] ?? null
              const delta = c != null && p != null ? c - p : null
              const deltaClass =
                delta == null ? '' : delta > 0 ? 'delta-pos' : delta < 0 ? 'delta-neg' : 'delta-zero'
              return (
                <div key={skill.id} className="cmp-row">
                  <span className="cmp-skill">{skill.label}</span>
                  <span className="cmp-cell">
                    <span className={`cmp-score ${c != null ? 'coach-chip' : 'empty'}`}>{c ?? '—'}</span>
                  </span>
                  <span className="cmp-cell">
                    <span className={`cmp-score ${p != null ? 'player-chip' : 'empty'}`}>{p ?? '—'}</span>
                  </span>
                  <span className={`cmp-cell cmp-delta ${deltaClass}`}>
                    {delta == null ? '—' : delta > 0 ? `+${delta}` : delta}
                  </span>
                </div>
              )
            })}
          </div>
        </div>
      ))}
    </div>
  )
}
