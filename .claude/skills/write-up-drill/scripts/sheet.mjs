// A review sheet for drills in a data file: every diagram as a row of frames, one per step, each at the step's
// start with its arrows, and which versions use it. For checking diagrams yourself and sending to the user.
//
//   node .claude/skills/write-up-drill/scripts/sheet.mjs backend/app/data/drills_vN.json OUT.html [slug ...]
//   node .claude/skills/write-up-drill/scripts/shot.mjs OUT.html OUT.png   (a PNG of it; see shot.mjs)
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../../../..')
const { buildTimeline, frameAt, stepArrows } = await import(path.join(root, 'frontend/src/diagramModel.js'))
const [file, out, ...only] = process.argv.slice(2)
if (!file || !out) { console.error('usage: sheet.mjs DRILLS.json OUT.html [slug ...]'); process.exit(2) }
const data = JSON.parse(fs.readFileSync(file, 'utf8'))
const COLORS = { A: '#2a78d6', B: '#eb6834', N: '#6b7785' }
const KIND = { regression: 'Easier', base: 'Base', escalator: 'Harder' }
const esc = s => String(s ?? '').replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' })[c])

function frame(diagram, timeline, index) {
  const k = 200 / Math.max(diagram.pitch.width, diagram.pitch.length), P = 10
  const W = diagram.pitch.width * k + 2 * P, H = diagram.pitch.length * k + 2 * P
  const px = p => [p[0] * k + P, p[1] * k + P]
  const state = frameAt(timeline, index, 0)
  let svg = `<svg width="${W}" height="${H}"><rect width="${W}" height="${H}" fill="#3f8f4f"/><rect x="${P}" y="${P}" width="${diagram.pitch.width * k}" height="${diagram.pitch.length * k}" fill="none" stroke="#fff"/>`
  for (const g of diagram.pitch.goals ?? []) { const [x, y] = px(g.at); svg += `<rect x="${x - (g.width ?? 3) * k / 2}" y="${y - 3}" width="${(g.width ?? 3) * k}" height="6" fill="#fff"/>` }
  for (const a of stepArrows(timeline, index)) {
    const [x1, y1] = px(a.from), [x2, y2] = px(a.to)
    svg += `<line x1="${x1}" y1="${y1}" x2="${x2}" y2="${y2}" stroke="${a.kind === 'run' ? '#fff' : '#ffe08a'}" stroke-width="2"${a.kind === 'run' ? ' stroke-dasharray="5 3"' : a.kind === 'dribble' ? ' stroke-dasharray="2 2"' : ''}/><circle cx="${x2}" cy="${y2}" r="2.5" fill="#ffe08a"/>`
  }
  for (const [name, o] of Object.entries(diagram.objects)) {
    if (o.type === 'ball') continue
    const [x, y] = px(state.positions[name])
    if (o.type === 'cone') svg += `<path d="M${x} ${y - 5}L${x + 4} ${y + 3}L${x - 4} ${y + 3}Z" fill="orange"/>`
    else if (o.type === 'wall') { const [x2, y2] = px(o.to); svg += `<line x1="${x}" y1="${y}" x2="${x2}" y2="${y2}" stroke="#b9a58c" stroke-width="6"/>` }
    else if (o.type === 'mannequin') svg += `<rect x="${x - 3}" y="${y - 7}" width="6" height="14" fill="#d9dee3"/>`
    else svg += `<circle cx="${x}" cy="${y}" r="8" fill="${COLORS[o.team] ?? COLORS.N}"/><text x="${x}" y="${y + 3}" fill="#fff" font-size="8" text-anchor="middle">${esc(o.label ?? name)}</text>`
  }
  if (state.ball) { const [x, y] = px(state.ball); svg += `<circle cx="${x}" cy="${y}" r="3.5" fill="#fff" stroke="#000"/>` }
  return svg + '</svg>'
}

// The diagram a version shows: its own, else the nearest towards the base (as variationDiagram in the app does).
function shownDiagram(d, index, first) {
  while (index >= 0 && index < d.variations.length) {
    const v = d.variations[index]
    if (v.diagram !== undefined) return v.diagram
    if (v.kind === 'escalator') index -= 1
    else if (v.kind === 'regression') index += 1
    else break
  }
  return first
}

let html = '<!doctype html><meta charset="utf-8"><body style="font:12px sans-serif;background:#fff;margin:12px">'
for (const d of data.drills) {
  if (only.length && !only.includes(d.slug)) continue
  html += `<h2 style="margin:18px 0 4px">${esc(d.title)} <small style="color:#666">${esc(d.slug)}</small></h2>`
  const diagrams = d.media.map((m, i) => [m, i]).filter(([m]) => m.kind === 'diagram')
  if (!diagrams.length) html += '<p style="color:#a33">No diagram.</p>'
  for (const [m, i] of diagrams) {
    const users = d.variations.filter((v, j) => shownDiagram(d, j, diagrams[0][1]) === i).map(v => `${KIND[v.kind]}: ${v.title}`)
    const timeline = buildTimeline(m.diagram)
    html += `<h3 style="margin:10px 0 4px">${esc(m.caption)} <small style="color:#666">(used by ${esc(users.join('; ') || 'versions inheriting it')})</small></h3><div style="display:flex;flex-wrap:wrap;gap:8px">`
    timeline.steps.forEach((s, j) => { html += `<div style="width:220px">${frame(m.diagram, timeline, j)}<div>${j + 1}. ${esc(s.label)}</div></div>` })
    html += '</div>'
  }
}
fs.writeFileSync(out, html + '</body>')
console.log(`wrote ${out}`)
