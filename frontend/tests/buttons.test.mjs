import assert from 'node:assert/strict'
import fs from 'node:fs'
import path from 'node:path'
import { test } from 'node:test'

// A button's colour says what it does (primary-btn, secondary-btn, danger-btn, link-btn), never where it sits.
// Controls (tabs, toggles, navigation, pagers, chips) are styled by their own container.
const CONTROLS = ['.view-tabs', '.toggle-group', '.priority-help-heading', '.side-nav', '.sidebar-account', '.subtabs', '.context-sheet-heading',
  '.bottom-nav', '.assessment-accordion', '.skill-pager', '.matrix-outline', '.drill-ladder', '.diagram-controls', '.drill-vote', '.plan-weeks',
  '.queue-tabs', '.focus-chips']

const files = dir => fs.readdirSync(dir, { withFileTypes: true }).flatMap(e => e.isDirectory() ? files(path.join(dir, e.name)) : [path.join(dir, e.name)])

test('every button says what it is with a class', () => {
  const missing = []
  for (const file of files('src').filter(f => f.endsWith('.jsx'))) {
    const source = fs.readFileSync(file, 'utf8')
    for (const m of source.matchAll(/<button\b([^>]*?)>/gs)) {
      if (!/className=/.test(m[1])) missing.push(`${file}:${source.slice(0, m.index).split('\n').length}`)
    }
  }
  assert.deepEqual(missing, [], 'give these buttons primary-btn, secondary-btn, danger-btn, link-btn or a control class')
})

test('only controls are coloured by where they sit', () => {
  const css = fs.readFileSync('src/App.css', 'utf8') + fs.readFileSync('src/index.css', 'utf8')
  const offenders = []
  for (const m of css.matchAll(/([^{}]+)\{([^{}]*)\}/g)) {
    if (!/(^|;)\s*(background|color|border)\s*:/.test(m[2])) continue
    for (const selector of m[1].split(',').map(s => s.trim().replace(/\s+/g, ' '))) {
      if (/(^|[\s>])button(:\S*|\.active)?$/.test(selector) && !CONTROLS.some(c => selector.startsWith(c))) offenders.push(selector)
    }
  }
  assert.deepEqual(offenders, [], 'set colours with a role class on the button, not a container rule')
})
