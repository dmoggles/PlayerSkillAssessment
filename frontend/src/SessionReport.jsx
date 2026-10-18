import { useMemo } from 'react'
import { DiagramFrame } from './DiagramPlayer'
import { buildTimeline } from './diagramModel'
import { equipmentLabel, playersText } from './drillModel'
import { PHASE_NAMES, blockTimes, reportBlock, sessionDate, sessionEquipment } from './sessionModel'

// The session on paper, for taking to training: what to bring, the timeline, each drill with its set-up, steps,
// coaching points and diagram, a register to tick, and space for notes. Only shown when printing.
// `drills` holds each block's drill in full, by slug; a block whose drill hasn't loaded prints its title only.
export default function SessionReport({ session, teamName, drills }) {
  const times = blockTimes(session.blocks, session.start_time)
  const ends = blockTimes([...session.blocks, { minutes: 0 }], session.start_time).slice(1)
  const groups = session.versions === 'groups' ? session.groups : null
  const blocks = session.blocks.map(block => reportBlock(block, drills[block.drill?.slug], groups))
  const equipment = sessionEquipment(blocks)
  const groupOf = Object.fromEntries((groups ?? []).flatMap(g => g.players.map(p => [p.id, g.name])))
  const register = session.attendance.filter(r => r.expected || r.attended)
  return <article className="session-report">
    <header className="report-head">
      <p className="report-kicker">{teamName} · Training session</p>
      <h1>{session.title}</h1>
      <p>{sessionDate(session.date, session.start_time)} · {session.length} minutes{session.template ? ` · ${session.template.name}` : ''} · {session.expected} players expected</p>
      <p><strong>Focus:</strong> {session.focus.map(f => f.label).join(', ')}</p>
    </header>

    <section className="report-overview">
      <table className="report-timeline">
        <thead><tr><th>Time</th><th>Min</th><th>Part</th><th>Activity</th></tr></thead>
        <tbody>{session.blocks.map((b, i) => <tr key={b.id}>
          <td>{times[i]}</td><td>{b.minutes}</td><td>{PHASE_NAMES[b.phase]}</td><td>{b.drill ? b.drill.title : b.title}</td>
        </tr>)}</tbody>
      </table>
      {equipment.length > 0 && <div className="report-equipment"><h2>Bring</h2>
        <ul>{equipment.map(e => <li key={e.item}><span className="report-box" />{amount(e)}</li>)}</ul>
      </div>}
    </section>

    {groups && <section className="report-groups"><h2>Level groups</h2>
      {groups.map(g => <p key={g.name}><strong>{g.name}:</strong> {g.players.map(p => p.name).join(', ') || 'Nobody'}</p>)}
    </section>}

    {blocks.map((b, i) => <section key={b.block.id} className="report-block">
      <h2><span className="report-block-time">{times[i]}–{ends[i]}</span> {PHASE_NAMES[b.block.phase]} · {b.block.minutes} min</h2>
      <h3>{b.title}</h3>
      {b.together && <p className="report-together">Everyone together</p>}
      {b.versions.map(v => <p key={v.label} className="report-version"><strong>{v.label}</strong>{v.change ? ` ${v.change}` : ''}</p>)}
      {b.drill && <BlockDetail detail={b} />}
      {b.block.notes ? <p className="report-note"><strong>Note:</strong> {b.block.notes}</p> : <WriteLines label="Notes" count={b.drill ? 2 : 4} />}
    </section>)}

    <section className="report-register">
      <h2>Register</h2>
      <table>
        <thead><tr><th>Player</th>{groups && <th>Group</th>}<th>Came</th></tr></thead>
        <tbody>{register.map(r => <tr key={r.player_id}><td>{r.name}</td>{groups && <td>{groupOf[r.player_id] ?? ''}</td>}<td><span className="report-box" /></td></tr>)}
          {[0, 1, 2].map(n => <tr key={`extra-${n}`} className="report-extra"><td /> {groups && <td />}<td><span className="report-box" /></td></tr>)}</tbody>
      </table>
    </section>

    <section className="report-notes">
      <h2>How did it go?</h2>
      {session.notes ? <p>{session.notes}</p> : <WriteLines count={5} />}
    </section>
  </article>
}

// "16 balls", "1 goal": a quantity and the item, singular for one.
const amount = ({ item, quantity }) => {
  const label = equipmentLabel(item)
  return quantity ? `${quantity} ${quantity === 1 ? label.replace(/s$/, '') : label}` : label
}

function BlockDetail({ detail }) {
  const { content, diagram, drill } = detail
  const facts = [content.players && playersText(content.players), content.space && `${content.space[0]} × ${content.space[1]} m`,
    content.equipment?.length && content.equipment.map(amount).join(', ')].filter(Boolean)
  return <div className="report-detail">
    <div className="report-text">
      {facts.length > 0 && <p className="report-facts">{facts.join(' · ')}</p>}
      {content.setup && <p><strong>Set-up:</strong> {content.setup}</p>}
      {content.instructions?.length > 0 && <ol>{content.instructions.map(step => <li key={step}>{step}</li>)}</ol>}
      {content.coaching_points?.length > 0 && <><p className="report-label">Coaching points</p><ul>{content.coaching_points.map(point => <li key={point}>{point}</li>)}</ul></>}
    </div>
    {diagram && <Storyboard diagram={diagram.diagram} caption={diagram.caption} title={drill.title} />}
  </div>
}

// Every step of a diagram side by side, each at its start with its arrows: the paper version of the animation.
function Storyboard({ diagram, caption, title }) {
  const timeline = useMemo(() => buildTimeline(diagram), [diagram])
  return <figure className="report-storyboard">
    <div className="report-frames">{timeline.steps.map((step, i) => <div key={i} className="report-frame">
      <DiagramFrame diagram={diagram} timeline={timeline} index={i} progress={0} variant="paper" label={`${title}, step ${i + 1}: ${step.label}`} />
      <p><strong>{i + 1}.</strong> {step.label}</p>
    </div>)}</div>
    {caption && <figcaption>{caption}</figcaption>}
  </figure>
}

function WriteLines({ label, count }) {
  return <div className="report-lines">{label && <p className="report-label">{label}</p>}{Array.from({ length: count }, (_, i) => <span key={i} />)}</div>
}

