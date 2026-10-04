import { revisionTimeline, skillLabels } from './revisionModel'

export default function RevisionHistory({ matrix, revisions }) {
  if (!revisions.length) return null
  const timeline = revisionTimeline(revisions, skillLabels(matrix))
  return <details className="revisions"><summary>Revision history ({revisions.length})</summary>
    <ol className="revision-list">{timeline.map(revision => <li key={revision.version}>
      <div className="revision-heading"><strong>Version {revision.version}</strong><span>{revision.editor} · {new Date(revision.created_at).toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' })}</span></div>
      {revision.changes.length ? <ul>{revision.changes.map(change => <li key={change}>{change}</li>)}</ul> : <p className="muted">Saved with no changes</p>}
    </li>)}</ol>
  </details>
}
