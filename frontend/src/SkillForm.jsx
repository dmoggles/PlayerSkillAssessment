import { useState } from 'react'
import { sectionsFor, scalePoints, scaleAnchors } from './matrix'

export const UNKNOWN = 'unknown'

// Coach-only note on one rating: collapsed to an "Add note" button until used.
function SkillNote({ label, value, onChange, readOnly }) {
  const [open, setOpen] = useState(false)
  if (readOnly) return value ? <p className="skill-note-text">Note: {value}</p> : null
  if (!open && !value) return <button type="button" className="skill-note-add" onClick={() => setOpen(true)}>Add note</button>
  return <label className="skill-note">Note <small>Coach only</small><textarea rows={2} maxLength={500} aria-label={`Note on ${label}`} autoFocus={open && !value} value={value} onChange={e => onChange(e.target.value)} /></label>
}

export default function SkillForm({ matrix, position, ratings, onChange, notes = {}, onNoteChange = null, readOnly = false, allowUnknown = false, sectionId = null, skillId = null, showSectionTitle = true }) {
  const relevantSections = sectionsFor(matrix, position).filter(section => sectionId === null || section.id === sectionId)
  const SCALE = scalePoints(matrix)
  const ANCHOR_LABELS = scaleAnchors(matrix)

  return (
    <div className="skill-form">
      {relevantSections.map(section => (
        <div key={section.id} className="section">
          {showSectionTitle && <h3>{section.label}</h3>}
          {section.skills.filter(skill => skillId === null || skill.id === skillId).map(skill => {
            const score = ratings[skill.id] ?? null
            return (
              <div key={skill.id} className="skill-row">
                <div className="skill-header">
                  <span className="skill-label">{skill.label}</span>
                </div>
                <div className="option-buttons">
                  {SCALE.map(n => {
                    const descriptor = skill.descriptors[n]
                    const isAnchor = descriptor !== undefined
                    return (
                      <button
                        key={n}
                        type="button"
                        disabled={readOnly}
                        className={`option-btn ${isAnchor ? 'anchor' : 'intermediate'} ${score === n ? 'selected' : ''}`}
                        onClick={() => !readOnly && onChange(skill.id, score === n ? null : n)}
                      >
                        <span className="option-num">{n}</span>
                        {isAnchor ? (
                          <span className="option-text">
                            <span className="option-anchor-label">{ANCHOR_LABELS[n]}</span>
                            <span className="option-descriptor">{descriptor}</span>
                          </span>
                        ) : (
                          <span className="option-text option-intermediate-text">In between</span>
                        )}
                      </button>
                    )
                  })}
                  {allowUnknown && (
                    <button
                      type="button"
                      disabled={readOnly}
                      className={`option-btn unknown ${score === UNKNOWN ? 'selected' : ''}`}
                      onClick={() => !readOnly && onChange(skill.id, score === UNKNOWN ? null : UNKNOWN)}
                    >
                      <span className="option-num">?</span>
                      <span className="option-text option-intermediate-text">I don't know</span>
                    </button>
                  )}
                </div>
                {onNoteChange && <SkillNote label={skill.label} value={notes[skill.id] ?? ''} readOnly={readOnly} onChange={note => onNoteChange(skill.id, note)} />}
              </div>
            )
          })}
        </div>
      ))}
    </div>
  )
}
