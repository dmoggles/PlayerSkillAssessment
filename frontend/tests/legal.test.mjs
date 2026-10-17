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

test('the landing page explains the app, links to sign-in and offers a request form', async () => {
  const { default: Landing } = await loadJsx('src/site/Landing.jsx')
  const landing = user => {
    const router = createMemoryRouter([{ path: '*', element: React.createElement(Landing, { user }) }])
    return renderToStaticMarkup(React.createElement(RouterProvider, { router }))
  }
  const visitor = landing(null)
  assert.match(visitor, /<h1>A development plan for every player<\/h1>/)
  assert.match(visitor, /id="how-it-works"/)
  assert.match(visitor, /id="request-access"/)
  assert.match(visitor, /href="\/sign-in"/)
  assert.match(visitor, /Your name/)
  assert.match(visitor, /class="access-trap" aria-hidden="true"/)
  for (const src of ['/landing/plan.jpg', '/landing/progress.jpg', '/landing/drill.jpg']) assert.match(visitor, new RegExp(`src="${src}"`))
  // Signed-in coaches get a way back to their workspace instead of "Sign in".
  const coach = landing({ email: 'coach@example.com' })
  assert.match(coach, /href="\/app\/assessment"[^>]*>Open your workspace/)
  assert.doesNotMatch(coach, /class="site-cta" href="\/sign-in"/)
  assert.match(await render('privacy'), /If you request access/, 'the privacy notice covers what the form collects')
})
