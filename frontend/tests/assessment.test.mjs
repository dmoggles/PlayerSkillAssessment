import assert from 'node:assert/strict'
import { test } from 'node:test'
import React from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { assessmentSignature } from '../src/dashboardModel.js'
import { horizontalSwipe, ratedCount } from '../src/mobileAssessmentModel.js'
import { loadJsx } from './helpers.mjs'

test('mobile assessment shows one full-description skill and section completion', async () => {
  const { default: MobileAssessment } = await loadJsx('src/MobileAssessment.jsx')
  const technical = { id: 'technical', label: 'Technical Skills', applies_to: ['defender'], skills: [
    { id: 'touch', label: 'First touch', descriptors: { 1: 'Developing description', 3: 'Achieving description', 5: 'Excelling description' } },
    { id: 'passing', label: 'Passing', descriptors: { 1: 'Passes late', 3: 'Passes well', 5: 'Passes early' } },
  ] }
  const tactical = { id: 'tactical', label: 'Tactical Skills', applies_to: ['defender'], skills: [{ id: 'positioning', label: 'Positioning', descriptors: { 1: 'Lost', 3: 'Aware', 5: 'Anticipates' } }] }
  const matrix = { sections: [technical, tactical], meta: { scale: { points: [1, 2, 3, 4, 5], anchors: { 1: 'Developing', 3: 'Achieving', 5: 'Excelling' } } } }
  const html = renderToStaticMarkup(React.createElement(MobileAssessment, { matrix, position: 'outfield', ratings: { touch: 3 }, onChange: () => {} }))
  assert.equal(ratedCount(technical, { touch: 3 }), 1)
  assert.match(html, /1 of 3 skills rated/)
  assert.match(html, /1\/2 rated/)
  assert.match(html, /Technical Skills/)
  assert.match(html, /Tactical Skills/)
  assert.match(html, /Developing description/)
  assert.match(html, /Achieving description/)
  assert.match(html, /Excelling description/)
  assert.doesNotMatch(html, /Passes late/)
  assert.doesNotMatch(html, /Anticipates/)
  assert.equal(horizontalSwipe({ x: 180, y: 80 }, { x: 70, y: 90 }), 1)
  assert.equal(horizontalSwipe({ x: 70, y: 90 }, { x: 180, y: 80 }), -1)
  assert.equal(horizontalSwipe({ x: 180, y: 80 }, { x: 70, y: 160 }), 0)
})

test('unfiltered skill form still renders every applicable skill for desktop and self-assessment', async () => {
  const { default: SkillForm } = await loadJsx('src/SkillForm.jsx')
  const matrix = { sections: [{ id: 'technical', label: 'Technical', applies_to: ['defender'], skills: [
    { id: 'touch', label: 'First touch', descriptors: { 1: 'Needs control', 3: 'Controls well', 5: 'Controls under pressure' } },
    { id: 'passing', label: 'Passing', descriptors: { 1: 'Late pass', 3: 'Good pass', 5: 'Early pass' } },
  ] }], meta: { scale: { points: [1, 2, 3, 4, 5], anchors: {} } } }
  const html = renderToStaticMarkup(React.createElement(SkillForm, { matrix, position: 'outfield', ratings: {}, onChange: () => {} }))
  assert.match(html, /First touch/)
  assert.match(html, /Passing/)
  assert.match(html, /Controls under pressure/)
  assert.match(html, /Early pass/)
})

test('archived players get a read-only assessment with a restore prompt', async () => {
  const { default: MobileAssessment } = await loadJsx('src/MobileAssessment.jsx')
  const { ArchivedNotice } = await loadJsx('src/areas/DashboardParts.jsx')
  const matrix = { sections: [{ id: 'technical', label: 'Technical', applies_to: ['defender'], skills: [
    { id: 'touch', label: 'First touch', descriptors: { 1: 'Needs control', 3: 'Controls well', 5: 'Controls under pressure' } },
  ] }], meta: { scale: { points: [1, 2, 3, 4, 5], anchors: {} } } }
  const props = { matrix, position: 'outfield', ratings: { touch: 3 }, onChange: () => {} }
  const editable = renderToStaticMarkup(React.createElement(MobileAssessment, props))
  const archived = renderToStaticMarkup(React.createElement(MobileAssessment, { ...props, readOnly: true }))
  assert.match(editable, /Save assessment/)
  assert.doesNotMatch(archived, /Save assessment/)
  assert.equal(archived.match(/class="option-btn[^"]*"/g)?.length, 5)
  assert.equal(archived.match(/<button type="button" disabled="" class="option-btn/g)?.length, 5)
  const notice = renderToStaticMarkup(React.createElement(ArchivedNotice, { player: { name: 'Kai' }, onRestore: () => {} }))
  assert.match(notice, /Kai is archived\./)
  assert.match(notice, /Restore player/)
})

test('coach notes affect the unsaved-changes check and appear in the form and revision history', async () => {
  const { assessmentSignature, formFromAssessment, formSignature } = await import('../src/dashboardModel.js')
  const { revisionChanges } = await loadJsx('src/revisionModel.js')
  const { default: SkillForm } = await loadJsx('src/SkillForm.jsx')
  const saved = { primary_position: 'defender', note: 'Good week', ratings: [{ skill_id: 'touch', score: 3, note: 'Heavy touch' }, { skill_id: 'passing', score: 2, note: null }] }
  const form = formFromAssessment(saved)
  assert.deepEqual(form.notes, { touch: 'Heavy touch' })
  const baseline = formSignature(form)
  assert.equal(assessmentSignature('defender', '', 'sometimes', form.ratings, { ...form.notes, passing: '  ' }, 'Good week '), baseline)
  assert.notEqual(assessmentSignature('defender', '', 'sometimes', form.ratings, { touch: 'Lighter touch' }, 'Good week'), baseline)
  assert.notEqual(assessmentSignature('defender', '', 'sometimes', form.ratings, form.notes, ''), baseline)
  assert.equal(formFromAssessment(null).note, '')
  // A new period starts from the player's previous positions, with no ratings or notes.
  const { previousCoachAssessment } = await import('../src/dashboardModel.js')
  const winger = { primary_position: 'winger', secondary_position: 'striker', secondary_position_frequency: 'often', ratings: [{ skill_id: 'touch', score: 4, note: 'x' }] }
  const keeper = { primary_position: 'goalkeeper', secondary_position: null, ratings: [] }
  const periods = [{ id: 3 }, { id: 2 }, { id: 1 }]
  const history = [{ period_id: 1, assessments: { coach: keeper } }, { period_id: 2, assessments: { coach: winger } }]
  assert.equal(previousCoachAssessment(history, periods, 3), winger)
  assert.equal(previousCoachAssessment(history, periods, 2), keeper, 'nearest earlier period, not the current one')
  assert.equal(previousCoachAssessment(history, periods, 1), winger, 'no earlier period: most recent')
  assert.equal(previousCoachAssessment([], periods, 3), null)
  const fresh = formFromAssessment(null, winger)
  assert.deepEqual([fresh.position, fresh.secondary, fresh.frequency, fresh.ratings, fresh.notes], ['winger', 'striker', 'often', {}, {}])
  assert.equal(formFromAssessment(null).position, 'defender')

  const labels = { touch: 'First touch', passing: 'Passing' }
  const after = { ...saved, note: null, ratings: [{ skill_id: 'touch', score: 3, note: 'Better' }, { skill_id: 'passing', score: 2, note: 'Look up first' }] }
  assert.deepEqual(revisionChanges(saved, after, labels), ['First touch note edited', 'Passing note added', 'Overall note removed'])

  const matrix = { sections: [{ id: 'technical', label: 'Technical', applies_to: ['defender'], skills: [
    { id: 'touch', label: 'First touch', descriptors: { 1: 'a', 3: 'b', 5: 'c' } }, { id: 'passing', label: 'Passing', descriptors: { 1: 'd', 3: 'e', 5: 'f' } },
  ] }], meta: { scale: { points: [1, 2, 3, 4, 5], anchors: {} } } }
  const base = { matrix, position: 'outfield', ratings: {}, onChange: () => {}, notes: { touch: 'Heavy touch' } }
  const editable = renderToStaticMarkup(React.createElement(SkillForm, { ...base, onNoteChange: () => {} }))
  assert.match(editable, /aria-label="Note on First touch"[^>]*>Heavy touch<\/textarea>/)
  assert.match(editable, /Add note/)
  const archived = renderToStaticMarkup(React.createElement(SkillForm, { ...base, onNoteChange: () => {}, readOnly: true }))
  assert.match(archived, /Note: Heavy touch/)
  assert.doesNotMatch(archived, /textarea|Add note/)
  assert.doesNotMatch(renderToStaticMarkup(React.createElement(SkillForm, base)), /Add note|textarea/)
})

test('carried ratings are tracked in the form, marked in the assessment and in Progress', async () => {
  const { formFromAssessment, formSignature } = await loadJsx('src/dashboardModel.js')
  const assessment = { primary_position: 'defender', ratings: [{ skill_id: 'a', score: 3, carried: true }, { skill_id: 'b', score: 4, carried: false }, { skill_id: 'c', score: null, carried: true }] }
  const form = formFromAssessment(assessment)
  assert.deepEqual(form.carried, ['a'], 'only scored, carried skills')
  assert.notEqual(formSignature(form), formSignature({ ...form, carried: [] }), 'reviewing a carried rating is an unsaved change')
  const { default: SkillForm } = await loadJsx('src/SkillForm.jsx')
  const matrix = { scale: { anchors: { 1: 'Developing', 3: 'Achieving', 5: 'Excelling' } }, sections: [{ id: 't', label: 'Technical', applies_to: ['defender'], skills: [{ id: 'a', label: 'Passing', descriptors: { 1: 'x', 3: 'y', 5: 'z' } }] }] }
  const html = renderToStaticMarkup(React.createElement(SkillForm, { matrix, position: 'outfield', ratings: { a: 3 }, onChange: () => {}, carried: ['a'], onKeepCarried: () => {} }))
  assert.match(html, /Carried from last period<\/span><button type="button" class="link-btn">Keep<\/button>/)
  const { default: ProgressView } = await loadJsx('src/ProgressView.jsx')
  const history = [{ period_id: 1, label: 'Fall', assessments: { coach: { ratings: [{ skill_id: 'a', score: 3 }] } } },
    { period_id: 2, label: 'Spring', assessments: { coach: { ratings: [{ skill_id: 'a', score: 3, carried: true }] } } }]
  const progress = renderToStaticMarkup(React.createElement(ProgressView, { matrix: { sections: [] }, history }))
  assert.match(progress, /3<sup class="carried-sup"/)
  assert.match(progress, /Carried from the previous period and not re-rated yet/)
})
