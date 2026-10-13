import assert from 'node:assert/strict'
import { test } from 'node:test'
import React from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { createMemoryRouter, RouterProvider } from 'react-router-dom'
import { loadJsx } from './helpers.mjs'

const render = async page => {
  const { default: LegalPage } = await loadJsx('src/legal/LegalPage.jsx')
  const router = createMemoryRouter([{ path: '*', element: React.createElement(LegalPage, { page }) }])
  return renderToStaticMarkup(React.createElement(RouterProvider, { router }))
}

test('the privacy notice names the club as controller, lists processors and links the other pages', async () => {
  const html = await render('privacy')
  assert.match(html, /<h1>Privacy notice<\/h1>/)
  assert.match(html, /club is the <em>controller<\/em>/)
  assert.match(html, /Resend/)
  assert.match(html, /within about three months/)
  for (const href of ['/privacy', '/privacy/players', '/terms']) assert.match(html, new RegExp(`href="${href}"`))
})

test('the terms include the data processing agreement, and the players\' notice speaks to players', async () => {
  assert.match(await render('terms'), /id="data-processing"[\s\S]*Article 28/)
  assert.match(await render('players'), /Your club uses TapLine IDP/)
})

// Reported, not failed: the operator's details are filled in by hand before release.
test('operator details still to fill in before release', async () => {
  const { OPERATOR, PROCESSORS } = await loadJsx('src/legal/operator.js')
  const missing = JSON.stringify([OPERATOR, PROCESSORS]).match(/\[[A-Z][A-Z ]+\]/g) ?? []
  if (missing.length) console.log(`Legal pages still need: ${[...new Set(missing)].join(', ')}`)
})
