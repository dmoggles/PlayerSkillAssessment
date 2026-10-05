import { useCallback, useEffect, useState } from 'react'
import { discardMatrixDraft, errorMessage, getMatrixDraft, getSkillTags, saveMatrixDraft } from './api'
import { POSITION_LABELS } from './matrix'
import * as m from './matrixEditorModel'

const AUTOSAVE_MS = 800
const AREA_LABELS = { technical: 'Technical', tactical: 'Tactical', mental: 'Mental', goalkeeping: 'Goalkeeping', physical: 'Physical' }

// Owner-only editor for the team's skill matrix. Edits autosave to a shared draft; publishing is a separate step.
export default function MatrixEditor({ teamId, onClose, onMessage }) {
  const [server, setServer] = useState(null)
  const [doc, setDoc] = useState(null)
  const [tags, setTags] = useState([])
  const [revision, setRevision] = useState(0)
  const [edits, setEdits] = useState(0)
  const [savedEdits, setSavedEdits] = useState(0)
  const [saving, setSaving] = useState(false)
  const [failure, setFailure] = useState(null)
  const [selected, setSelected] = useState(null)

  const load = useCallback(() => Promise.all([getMatrixDraft(teamId), getSkillTags()]).then(([draft, tagList]) => {
    setServer(draft); setDoc(draft.document); setRevision(draft.revision); setTags(tagList)
    setEdits(0); setSavedEdits(0); setFailure(null)
  }).catch(e => onMessage(errorMessage(e))), [teamId, onMessage])
  useEffect(() => { load() }, [load])

  // Autosave the latest document once editing pauses; one save at a time.
  useEffect(() => {
    if (!doc || saving || edits === savedEdits || failure === 'conflict') return
    const sentDoc = doc, sentEdits = edits
    const timer = setTimeout(async () => {
      setSaving(true)
      try {
        const result = await saveMatrixDraft(teamId, revision, sentDoc)
        setServer(result); setRevision(result.revision); setSavedEdits(sentEdits); setFailure(null)
        setDoc(current => current === sentDoc ? result.document : m.adoptServerIds(current, result.document))
      } catch (e) {
        const status = e?.response?.status
        setFailure(status === 409 ? 'conflict' : 'error')
        if (status === 422) setSavedEdits(sentEdits)
        onMessage(errorMessage(e))
      } finally { setSaving(false) }
    }, failure === 'error' ? AUTOSAVE_MS * 5 : AUTOSAVE_MS)
    return () => clearTimeout(timer)
  }, [doc, edits, savedEdits, saving, failure, revision, teamId, onMessage])

  const edit = fn => { setDoc(current => fn(current)); setEdits(n => n + 1) }
  const pending = edits !== savedEdits

  async function close() {
    if (pending && !saving && failure !== 'conflict') {
      try { await saveMatrixDraft(teamId, revision, doc) } catch (e) { onMessage(errorMessage(e)) }
    }
    onClose()
  }
  async function discard() {
    if (!window.confirm('Discard the draft? All unpublished changes to the skill matrix will be lost.')) return
    try { await discardMatrixDraft(teamId); setSelected(null); await load(); onMessage('Draft discarded.') } catch (e) { onMessage(errorMessage(e)) }
  }

  if (!doc || !server) return <p className="muted" role="status">Loading skill matrix…</p>

  const tagsById = Object.fromEntries(tags.map(t => [t.id, t]))
  const published = new Set(server.base_skill_ids)
  const found = selected ? m.findSkill(doc, selected) : null
  const status = failure === 'conflict' ? 'Changed by another owner' : saving ? 'Saving…' : pending ? 'Unsaved changes' : failure === 'error' ? 'Not saved, retrying' : server.draft ? 'Draft saved' : 'No changes yet'
  const anchors = doc.meta?.scale?.anchors ?? {}

  return <div className={`matrix-editor ${found ? 'has-selection' : ''}`}>
    <div className="matrix-editor-header">
      <button type="button" className="link-btn" onClick={close}>← Back to settings</button>
      <div><h2>Skill matrix</h2><p className="muted">Draft based on {server.current.name}, version {server.current.version}. Changes autosave and only affect new periods once published.</p></div>
      <div className="matrix-editor-actions">
        <span className={`save-status ${failure ? 'save-status-problem' : ''}`} role="status">{status}</span>
        {failure === 'conflict' && <button type="button" onClick={load}>Reload</button>}
        {server.draft && <button type="button" onClick={discard}>Discard draft</button>}
      </div>
    </div>

    <DraftSummary server={server} />

    <div className="matrix-editor-body">
      <nav className="matrix-outline" aria-label="Sections and skills">
        {doc.sections.map((section, sectionIndex) => {
          const sectionKey = m.keyOf(section)
          return <section key={sectionKey} className="matrix-outline-section">
            <div className="matrix-outline-section-head">
              <input aria-label="Section name" value={section.label} maxLength={80} onChange={e => edit(d => m.renameSection(d, sectionKey, e.target.value))} />
              <span className="status-pill muted-pill">{m.isGoalkeeperSection(section) ? 'Goalkeepers' : 'Outfield'}</span>
              <div className="item-actions">
                <button type="button" aria-label={`Move ${section.label} up`} disabled={sectionIndex === 0} onClick={() => edit(d => m.moveSection(d, sectionKey, -1))}>↑</button>
                <button type="button" aria-label={`Move ${section.label} down`} disabled={sectionIndex === doc.sections.length - 1} onClick={() => edit(d => m.moveSection(d, sectionKey, 1))}>↓</button>
                {!section.skills.length && <button type="button" onClick={() => edit(d => m.removeSection(d, sectionKey))}>Remove</button>}
              </div>
            </div>
            <ul>{section.skills.map(skill => {
              const key = m.keyOf(skill)
              const isNew = !skill.id || !published.has(skill.id)
              const flagged = !Object.keys(skill.tags ?? {}).length || m.LEVELS.some(l => !skill.descriptors[l]?.trim() || m.literalPronouns(skill.descriptors[l]).length)
              return <li key={key}><button type="button" className={selected === key ? 'active' : ''} aria-current={selected === key ? 'true' : undefined} onClick={() => setSelected(key)}>
                <span>{skill.label || 'Unnamed skill'}</span>{isNew && <span className="status-pill info-pill">New</span>}{flagged && <span className="status-pill warn-pill" title="Needs attention">!</span>}
              </button></li>
            })}</ul>
            <button type="button" className="link-btn" onClick={() => { const [next, key] = m.addSkill(doc, sectionKey); edit(() => next); setSelected(key) }}>+ Add skill</button>
          </section>
        })}
        <div className="inline-row"><button type="button" onClick={() => edit(d => m.addSection(d, 'outfield')[0])}>+ Outfield section</button><button type="button" onClick={() => edit(d => m.addSection(d, 'goalkeeper')[0])}>+ Goalkeeper section</button></div>
      </nav>

      <div className="matrix-skill">
        {!found ? <p className="muted">Choose a skill to edit it, or add a new one.</p>
          : <SkillEditor doc={doc} found={found} anchors={anchors} tags={tags} tagsById={tagsById} published={published}
            onEdit={edit} onBack={() => setSelected(null)} onRemoved={() => setSelected(null)} />}
      </div>
    </div>
  </div>
}

function DraftSummary({ server }) {
  const total = m.changeCount(server.changes)
  return <section className="matrix-summary" aria-label="Draft summary">
    <p><strong>{total ? `${total} ${total === 1 ? 'change' : 'changes'}` : 'No changes'}</strong> compared with the published matrix{server.problems.length ? ` · ${server.problems.length} to fix before publishing` : ''}{server.warnings.length ? ` · ${server.warnings.length} wording ${server.warnings.length === 1 ? 'warning' : 'warnings'}` : ''}</p>
    {(total > 0 || server.problems.length > 0 || server.warnings.length > 0) && <details>
      <summary>Show details</summary>
      {server.problems.length > 0 && <div className="matrix-summary-group problem"><h4>Fix before publishing</h4><ul>{server.problems.map(p => <li key={p}>{p}</li>)}</ul></div>}
      {server.warnings.length > 0 && <div className="matrix-summary-group warning"><h4>Pronouns <small>Use placeholders so wording follows the Players setting.</small></h4><ul>{server.warnings.map(w => <li key={w}>{w}</li>)}</ul></div>}
      {m.CHANGE_GROUPS.filter(([kind]) => server.changes[kind]?.length).map(([kind, label, note]) => <div key={kind} className={`matrix-summary-group change-${kind}`}><h4>{label} <small>{note}</small></h4><ul>{server.changes[kind].map(c => <li key={c}>{c}</li>)}</ul></div>)}
    </details>}
  </section>
}

function SkillEditor({ doc, found, anchors, tags, tagsById, published, onEdit, onBack, onRemoved }) {
  const { skill, section } = found
  const key = m.keyOf(skill)
  const keeper = m.isGoalkeeperSection(section)
  const siblings = doc.sections.filter(s => m.isGoalkeeperSection(s) === keeper)
  const candidates = siblings.flatMap(s => s.skills).filter(s => s.id && m.keyOf(s) !== key)
  const foundationFor = skill.id ? doc.dependency_map?.[skill.id] ?? [] : []
  const mainTags = Object.entries(skill.tags ?? {}).filter(([, w]) => w === 1).map(([id]) => tagsById[id]).filter(Boolean)
  const isPublished = skill.id && published.has(skill.id)
  const index = section.skills.findIndex(s => m.keyOf(s) === key)
  const available = tags.filter(t => t.active && !(t.id in (skill.tags ?? {})))

  function remove() {
    const question = isPublished
      ? `Retire ${skill.label}? It will not be rated in new periods. Past ratings are kept, but comparisons across periods will lose this skill.`
      : `Delete ${skill.label}? It has not been published yet.`
    if (!window.confirm(question)) return
    onEdit(d => m.removeSkill(d, key)); onRemoved()
  }

  return <div className="skill-editor">
    <button type="button" className="link-btn skill-editor-back" onClick={onBack}>← All skills</button>
    <label className="field">Skill name<input value={skill.label} maxLength={80} onChange={e => onEdit(d => m.updateSkill(d, key, { label: e.target.value }))} /></label>
    <div className="inline-row skill-editor-place">
      <label className="field">Section<select value={m.keyOf(section)} onChange={e => onEdit(d => m.moveSkillToSection(d, key, e.target.value))}>{siblings.map(s => <option key={m.keyOf(s)} value={m.keyOf(s)}>{s.label}</option>)}</select></label>
      <div className="item-actions"><button type="button" disabled={index === 0} onClick={() => onEdit(d => m.moveSkill(d, key, -1))}>Move up</button><button type="button" disabled={index === section.skills.length - 1} onClick={() => onEdit(d => m.moveSkill(d, key, 1))}>Move down</button></div>
    </div>

    <fieldset className="skill-editor-group"><legend>Level descriptions</legend>
      <p className="muted hint">Use {'{they}'}, {'{them}'}, {'{their}'}, {'{themself}'} for the player, and pairs such as {'{is|are}'} for verbs, so wording follows the team's Players setting.</p>
      {m.LEVELS.map(level => {
        const words = m.literalPronouns(skill.descriptors[level] ?? '')
        return <div className="level-row" key={level}>
          <label className="field">Level {level}{anchors[level] ? ` · ${anchors[level]}` : ''}<textarea rows={2} maxLength={300} value={skill.descriptors[level] ?? ''} onChange={e => onEdit(d => m.setDescriptor(d, key, level, e.target.value))} /></label>
          {words.length > 0 && <p className="warning-text">Use placeholders instead of: {words.join(', ')}</p>}
          {mainTags.map(tag => <p className="tag-guide" key={tag.id}><span>{tag.label} guide:</span> {tag[`level_${level}`]}</p>)}
        </div>
      })}
    </fieldset>

    <fieldset className="skill-editor-group"><legend>Skill tags</legend>
      <p className="muted hint">Tags connect this skill to drills and training plans. Choose one Main tag; add Partial tags for anything else it clearly involves.</p>
      <ul className="tag-list">{Object.entries(skill.tags ?? {}).map(([id, weight]) => <li key={id}>
        <span>{tagsById[id]?.label ?? id}{tagsById[id] && !tagsById[id].active ? ' (retired)' : ''}</span>
        <select aria-label={`Weight for ${tagsById[id]?.label ?? id}`} value={weight} onChange={e => onEdit(d => m.setTag(d, key, id, Number(e.target.value)))}>{m.TAG_WEIGHTS.map(([w, label]) => <option key={w} value={w}>{label}</option>)}</select>
        <button type="button" onClick={() => onEdit(d => m.setTag(d, key, id, null))}>Remove</button>
      </li>)}</ul>
      <label className="field">Add a tag<select value="" onChange={e => { if (e.target.value) onEdit(d => m.setTag(d, key, e.target.value, Object.keys(skill.tags ?? {}).length ? 0.5 : 1)) }}>
        <option value="">Choose a tag…</option>
        {Object.entries(AREA_LABELS).map(([area, label]) => <optgroup key={area} label={label}>{available.filter(t => t.area === area).map(t => <option key={t.id} value={t.id}>{t.label}</option>)}</optgroup>)}
      </select></label>
    </fieldset>

    <fieldset className="skill-editor-group"><legend>Importance by position</legend>
      <p className="muted hint">Used when suggesting priorities: important skills for a player's position rank higher.</p>
      <div className="importance-grid">{Object.keys(skill.position_weights).map(position => <label key={position} className="field">{POSITION_LABELS[position] ?? position}
        <select value={skill.position_weights[position]} onChange={e => onEdit(d => m.setImportance(d, key, position, e.target.value))}>{m.IMPORTANCE.map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label>)}</div>
    </fieldset>

    <fieldset className="skill-editor-group"><legend>Foundation for</legend>
      {!skill.id ? <p className="muted hint">Available once the new skill has saved.</p> : <>
        <p className="muted hint">If any of these skills is weak, {skill.label || 'this skill'} gets a boost when suggesting priorities.</p>
        <div className="foundation-list">{candidates.map(c => <label key={c.id} className="checkbox"><input type="checkbox" checked={foundationFor.includes(c.id)}
          onChange={e => onEdit(d => m.setFoundationFor(d, skill.id, e.target.checked ? [...foundationFor, c.id] : foundationFor.filter(id => id !== c.id)))} /> {c.label}</label>)}</div>
      </>}
    </fieldset>

    <div className="skill-editor-danger"><button type="button" className="danger-btn" onClick={remove}>{isPublished ? 'Retire skill' : 'Delete skill'}</button></div>
  </div>
}
