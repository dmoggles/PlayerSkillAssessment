import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { test } from 'node:test'
import { loadJsx } from './helpers.mjs'

const formats = JSON.parse(readFileSync(new URL('../../backend/app/data/practice_scenarios.json', import.meta.url))).formats
const [poll] = JSON.parse(readFileSync(new URL('../../backend/app/data/polls.json', import.meta.url))).polls
const withPitch = s => ({ ...s, pitch: { ...formats[s.format], penaltyArea: { ...formats[s.format].penaltyArea } } })

test('a respondent keeps the same id in this browser, and still gets one without storage', async () => {
  const { respondentFor } = await loadJsx('src/poll/pollModel.js')
  const kept = new Map()
  const storage = { getItem: k => kept.get(k) ?? null, setItem: (k, v) => kept.set(k, v) }
  const first = respondentFor('p', storage)
  assert.match(first, /^[A-Za-z0-9-]{16,64}$/)
  assert.equal(respondentFor('p', storage), first)
  assert.notEqual(respondentFor('other', storage), first)
  const blocked = { getItem: () => { throw new Error('blocked') }, setItem: () => { throw new Error('blocked') } }
  assert.match(respondentFor('p', blocked), /^[A-Za-z0-9-]{16,64}$/)
})

test('answers group by the nearest reference spot, or somewhere else when none is near', async () => {
  const { ELSEWHERE, groupOf, tally } = await loadJsx('src/poll/pollModel.js')
  const spots = [{ label: 'Press', x: 20, y: 18 }, { label: 'Cover', x: 14, y: 20 }]
  assert.equal(groupOf({ x: 19, y: 18 }, spots), 'Press')
  assert.equal(groupOf({ x: 13, y: 21 }, spots), 'Cover')
  assert.equal(groupOf({ x: 2, y: 2 }, spots), ELSEWHERE)
  assert.deepEqual(tally([{ x: 19, y: 18 }, { x: 20, y: 17 }, { x: 13, y: 21 }], spots), [{ label: 'Press', n: 2 }, { label: 'Cover', n: 1 }])
  assert.deepEqual(tally([{ x: 2, y: 2 }], spots).at(-1), { label: ELSEWHERE, n: 1 })
})

test('every poll situation draws, with answers and spots on the admin\'s pitch', async () => {
  const { createElement } = await import('react')
  const { renderToStaticMarkup } = await import('react-dom/server')
  const { default: PracticePitch } = await loadJsx('src/practice/PracticePitch.jsx')
  assert.equal(poll.scenarios.length, 10)
  for (const raw of poll.scenarios) {
    const s = withPitch(raw)
    const shown = { ball: s.ball, team: s.team, opponents: s.opponents }
    const you = s.team.find(p => p.id === s.controlled)
    assert.ok(you && s.references.length >= 2, s.id)
    const answering = renderToStaticMarkup(createElement(PracticePitch, { scenario: s, shown, position: you, onMove: () => {}, youText: '?' }))
    assert.match(answering, /practice-you/)
    assert.match(answering, />\?</)
    assert.doesNotMatch(answering, />You</)
    const results = renderToStaticMarkup(createElement(PracticePitch, { scenario: s, shown, position: null, disabled: true,
      marks: [{ key: 'a', x: 10, y: 10, className: 'group-0' }], spots: s.references }))
    assert.doesNotMatch(results, /practice-you/)
    assert.match(results, /practice-mark group-0/)
    for (const r of s.references) assert.ok(results.includes(`>${r.label}<`), `${s.id}: ${r.label}`)
  }
})
