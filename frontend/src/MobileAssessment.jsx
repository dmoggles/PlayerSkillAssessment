import { useRef, useState } from 'react'
import SkillForm from './SkillForm'
import { sectionsFor } from './matrix'
import { horizontalSwipe, ratedCount } from './mobileAssessmentModel'

export default function MobileAssessment({ matrix, position, ratings, onChange, readOnly = false }) {
  const sections = sectionsFor(matrix, position)
  const [expandedId, setExpandedId] = useState(null)
  const [indexes, setIndexes] = useState({})
  const touchStart = useRef(null)
  const activeId = expandedId === '' ? '' : sections.some(section => section.id === expandedId) ? expandedId : sections[0]?.id
  const total = sections.reduce((sum, section) => sum + section.skills.length, 0)
  const rated = sections.reduce((sum, section) => sum + ratedCount(section, ratings), 0)

  function move(section, direction) {
    setIndexes(previous => ({
      ...previous,
      [section.id]: Math.max(0, Math.min(section.skills.length - 1, (previous[section.id] ?? 0) + direction)),
    }))
  }

  return <div className="mobile-assessment">
    <div className="mobile-assessment-progress"><strong>{rated} of {total} skills rated</strong><progress value={rated} max={total || 1} aria-label="Assessment progress" /></div>
    <div className="assessment-accordions">{sections.map(section => {
      const open = activeId === section.id
      const index = Math.min(indexes[section.id] ?? 0, section.skills.length - 1)
      const skill = section.skills[index]
      return <section className={`assessment-accordion ${open ? 'open' : ''}`} key={section.id}>
        <h3><button id={`assessment-heading-${section.id}`} type="button" aria-expanded={open} aria-controls={`assessment-panel-${section.id}`} onClick={() => setExpandedId(open ? '' : section.id)}><span>{section.label}</span><span className="accordion-meta">{ratedCount(section, ratings)}/{section.skills.length} rated <span aria-hidden="true" className="accordion-chevron">⌄</span></span></button></h3>
        {open && skill && <div id={`assessment-panel-${section.id}`} role="region" aria-labelledby={`assessment-heading-${section.id}`} className="assessment-accordion-panel">
          <div className="skill-card-top"><span>Skill {index + 1} of {section.skills.length}</span><span>{typeof ratings[skill.id] === 'number' ? `Rated ${ratings[skill.id]}/5` : 'Not rated'}</span></div>
          <div className="skill-swipe-region" tabIndex={0} aria-label={`${skill.label}. Swipe left or right, or use Previous and Next.`}
            onKeyDown={event => { if (event.key === 'ArrowRight') { event.preventDefault(); move(section, 1) } else if (event.key === 'ArrowLeft') { event.preventDefault(); move(section, -1) } }}
            onTouchStart={event => { const touch = event.changedTouches[0]; touchStart.current = { x: touch.clientX, y: touch.clientY } }}
            onTouchEnd={event => { const touch = event.changedTouches[0]; const direction = horizontalSwipe(touchStart.current, { x: touch.clientX, y: touch.clientY }); touchStart.current = null; if (direction) move(section, direction) }}
            onTouchCancel={() => { touchStart.current = null }}>
            <SkillForm matrix={matrix} position={position} ratings={ratings} onChange={onChange} readOnly={readOnly} sectionId={section.id} skillId={skill.id} showSectionTitle={false} />
          </div>
          <div className="skill-pager"><button type="button" onClick={() => move(section, -1)} disabled={index === 0} aria-label="Previous skill">← Previous</button><span aria-live="polite">{index + 1} / {section.skills.length}</span><button type="button" onClick={() => move(section, 1)} disabled={index === section.skills.length - 1} aria-label="Next skill">Next →</button></div>
        </div>}
      </section>
    })}</div>
    {!readOnly && <div className="mobile-assessment-save"><span>{rated === total ? 'All skills rated' : `${total - rated} still unrated`}</span><button type="submit">Save assessment</button></div>}
  </div>
}
