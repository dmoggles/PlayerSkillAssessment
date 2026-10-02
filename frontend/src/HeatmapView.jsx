import { useRef, useState } from 'react'
import { OUTFIELD_POSITIONS, POSITION_ABBR, sectionsFor, norm } from './matrix'
import { horizontalSwipe } from './mobileAssessmentModel'
import { columnsByScore } from './teamDataModel'

// Continuous red -> amber -> green scale for scores 1..5
const scoreColor = (score) => {
  if (score == null) return 'transparent'
  const t = Math.max(0, Math.min(1, (score - 1) / 4))
  const hue = t * 120 // 0 = red, 120 = green
  return `hsl(${hue}, 62%, 47%)`
}

const ratingsToMap = (assessment) => {
  const m = {}
  for (const r of assessment.ratings) m[r.skill_id] = r.score
  return m
}

const fmt = (v) => (v == null ? '' : Number.isInteger(v) ? String(v) : v.toFixed(1))

function FilterIcon({ name }) {
  const shapes = {
    individual: <><circle cx="12" cy="7" r="3" /><path d="M5 20c0-4 3-7 7-7s7 3 7 7" /></>,
    position: <><circle cx="12" cy="5" r="2" /><circle cx="5" cy="16" r="2" /><circle cx="19" cy="16" r="2" /><path d="M10.5 6.5 6.5 14M13.5 6.5l4 7.5M7 16h10" /></>,
    outfield: <><rect x="3" y="4" width="18" height="16" rx="1" /><path d="M12 4v16" /><circle cx="12" cy="12" r="3" /></>,
    goalkeeper: <><path d="M3 19V5h18v14M7 19v-4c0-3 2-5 5-5s5 2 5 5v4" /><circle cx="12" cy="7" r="2" /></>,
  }
  return <svg aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">{shapes[name]}</svg>
}

export default function HeatmapView({ matrix, assessments }) {
  const [level, setLevel] = useState('individual') // individual | position
  const [skillSet, setSkillSet] = useState('outfield') // outfield | goalkeeper
  const [expandedId, setExpandedId] = useState(null)
  const [indexes, setIndexes] = useState({})
  const touchStart = useRef(null)

  // Coach assessments only, matching the chosen skill set.
  const subjects = assessments.filter(a => a.assessor === 'coach' && a.position === skillSet)
  const sections = sectionsFor(matrix, skillSet)
  const activeId = expandedId === '' ? '' : sections.some(section => section.id === expandedId) ? expandedId : sections[0]?.id

  function move(section, direction) {
    setIndexes(previous => ({
      ...previous,
      [section.id]: Math.max(0, Math.min(section.skills.length - 1, (previous[section.id] ?? 0) + direction)),
    }))
  }

  // Build columns + a value lookup: valueFor(skillId, columnKey) -> number|null
  let columns = []
  let valueFor = () => null

  if (level === 'individual') {
    columns = subjects.map(a => ({ key: a.player_name, label: a.player_name, sub: POSITION_ABBR[norm(a.primary_position)] ?? '' }))
    const maps = Object.fromEntries(subjects.map(a => [a.player_name, ratingsToMap(a)]))
    valueFor = (skillId, key) => maps[key]?.[skillId] ?? null
  } else {
    const buckets = skillSet === 'goalkeeper' ? ['goalkeeper'] : OUTFIELD_POSITIONS
    const present = buckets.filter(b => subjects.some(a => norm(a.primary_position) === b))
    columns = present.map(b => ({
      key: b,
      label: POSITION_ABBR[b] ?? b,
      sub: `${subjects.filter(a => norm(a.primary_position) === b).length}`,
    }))
    const grouped = Object.fromEntries(
      present.map(b => [b, subjects.filter(a => norm(a.primary_position) === b).map(ratingsToMap)])
    )
    valueFor = (skillId, key) => {
      const vals = grouped[key].map(m => m[skillId]).filter(v => v != null)
      if (!vals.length) return null
      return vals.reduce((s, v) => s + v, 0) / vals.length
    }
  }

  return (
    <div className="heatmap">
      <div className="heatmap-controls">
        <div className="toggle-group" role="group" aria-label="Compare by">
          <button type="button" aria-label="Individual players" title="Individual players" aria-pressed={level === 'individual'} className={level === 'individual' ? 'active' : ''} onClick={() => setLevel('individual')}><FilterIcon name="individual" /><span className="heatmap-control-label">Individual</span></button>
          <button type="button" aria-label="By position" title="By position" aria-pressed={level === 'position'} className={level === 'position' ? 'active' : ''} onClick={() => setLevel('position')}><FilterIcon name="position" /><span className="heatmap-control-label">By Position</span></button>
        </div>
        <div className="toggle-group" role="group" aria-label="Skill set">
          <button type="button" aria-label="Outfield skills" title="Outfield skills" aria-pressed={skillSet === 'outfield'} className={skillSet === 'outfield' ? 'active' : ''} onClick={() => setSkillSet('outfield')}><FilterIcon name="outfield" /><span className="heatmap-control-label">Outfield</span></button>
          <button type="button" aria-label="Goalkeeper skills" title="Goalkeeper skills" aria-pressed={skillSet === 'goalkeeper'} className={skillSet === 'goalkeeper' ? 'active' : ''} onClick={() => setSkillSet('goalkeeper')}><FilterIcon name="goalkeeper" /><span className="heatmap-control-label">Goalkeeper</span></button>
        </div>
      </div>

      {columns.length === 0 ? (
        <p className="muted">No coach assessments for this skill set yet.</p>
      ) : <>
        <div className="heatmap-scroll desktop-data">
          <table className="heatmap-table">
            <thead>
              <tr>
                <th className="hm-skill-head">Skill</th>
                {columns.map(c => (
                  <th key={c.key} className="hm-col-head">
                    <span className="hm-col-label">{c.label}</span>
                    {c.sub && <span className="hm-col-sub">{c.sub}</span>}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {sections.map(section => (
                <SectionRows
                  key={section.id}
                  section={section}
                  columns={columns}
                  valueFor={valueFor}
                />
              ))}
            </tbody>
          </table>
        </div>
        <div className="mobile-data team-skill-sections">
          {sections.map(section => {
            const open = activeId === section.id
            const index = Math.min(indexes[section.id] ?? 0, section.skills.length - 1)
            const skill = section.skills[index]
            return <section key={section.id} className={`assessment-accordion ${open ? 'open' : ''}`}>
              <h3><button id={`team-heading-${section.id}`} type="button" aria-expanded={open} aria-controls={`team-panel-${section.id}`} onClick={() => setExpandedId(open ? '' : section.id)}><span>{section.label}</span><span className="accordion-meta">{section.skills.length} skills <span aria-hidden="true" className="accordion-chevron">⌄</span></span></button></h3>
              {open && skill && <div id={`team-panel-${section.id}`} role="region" aria-labelledby={`team-heading-${section.id}`} className="assessment-accordion-panel">
                <div className="skill-card-top"><span>Skill {index + 1} of {section.skills.length}</span><span>{columns.length} {level === 'position' ? 'positions' : columns.length === 1 ? 'player' : 'players'}</span></div>
                <div className="skill-swipe-region" tabIndex={0} aria-label={`${skill.label}. Swipe left or right, or use Previous and Next.`}
                  onKeyDown={event => { if (event.key === 'ArrowRight') { event.preventDefault(); move(section, 1) } else if (event.key === 'ArrowLeft') { event.preventDefault(); move(section, -1) } }}
                  onTouchStart={event => { const touch = event.changedTouches[0]; touchStart.current = { x: touch.clientX, y: touch.clientY } }}
                  onTouchEnd={event => { const touch = event.changedTouches[0]; const direction = horizontalSwipe(touchStart.current, { x: touch.clientX, y: touch.clientY }); touchStart.current = null; if (direction) move(section, direction) }}
                  onTouchCancel={() => { touchStart.current = null }}>
                  <article className="data-card team-skill-card">
                    <h4>{skill.label}</h4>
                    <dl>{columnsByScore(columns, skill.id, valueFor).map(column => {
                      const value = valueFor(skill.id, column.key)
                      return <div key={column.key}><dt>{column.label}{column.sub && <small>{level === 'position' ? ` · ${column.sub} players` : ` · ${column.sub}`}</small>}</dt><dd><span className="score-dot" style={{ backgroundColor: scoreColor(value) }} />{value == null ? 'Not rated' : fmt(value)}</dd></div>
                    })}</dl>
                  </article>
                </div>
                <div className="skill-pager"><button type="button" onClick={() => move(section, -1)} disabled={index === 0} aria-label="Previous skill">← Previous</button><span aria-live="polite">{index + 1} / {section.skills.length}</span><button type="button" onClick={() => move(section, 1)} disabled={index === section.skills.length - 1} aria-label="Next skill">Next →</button></div>
              </div>}
            </section>
          })}
        </div>
      </>}
    </div>
  )
}

function SectionRows({ section, columns, valueFor }) {
  return (
    <>
      <tr className="hm-section-row">
        <td colSpan={columns.length + 1}>{section.label}</td>
      </tr>
      {section.skills.map(skill => (
        <tr key={skill.id}>
          <td className="hm-skill">{skill.label}</td>
          {columns.map(c => {
            const v = valueFor(skill.id, c.key)
            return (
              <td
                key={c.key}
                className="hm-cell"
                style={{ background: scoreColor(v), color: v == null ? 'var(--muted)' : '#fff' }}
              >
                {fmt(v)}
              </td>
            )
          })}
        </tr>
      ))}
    </>
  )
}
