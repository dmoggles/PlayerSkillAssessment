import assert from 'node:assert/strict'
import { test } from 'node:test'
import React from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { createMemoryRouter, RouterProvider } from 'react-router-dom'
import { loadJsx } from './helpers.mjs'

const render = async path => {
  const { default: ManualPage } = await loadJsx('src/manual/ManualPage.jsx')
  const router = createMemoryRouter([{ path: '/manual', element: React.createElement(ManualPage, {}) }, { path: '/manual/:slug', element: React.createElement(ManualPage, {}) }], { initialEntries: [path] })
  return renderToStaticMarkup(React.createElement(RouterProvider, { router }))
}

test('every manual page has a title and summary, and links only to pages that exist', async () => {
  const { PAGES } = await loadJsx('src/manual/content.js')
  assert.ok(PAGES.length >= 10)
  assert.equal(PAGES[0].slug, 'getting-started')
  const slugs = new Set(PAGES.map(p => p.slug))
  const publicRoutes = new Set(['/', '/sign-in', '/privacy', '/privacy/players', '/terms', '/manual'])
  for (const page of PAGES) {
    assert.ok(page.title && page.summary, `${page.slug} needs a title and summary`)
    for (const [, href] of page.body.matchAll(/\]\(([^)]+)\)/g)) {
      if (href.startsWith('/manual/')) assert.ok(slugs.has(href.slice(8).split('#')[0]), `${page.slug} links to a missing page: ${href}`)
      else if (href.startsWith('/landing/')) continue
      else if (href.startsWith('/')) assert.ok(publicRoutes.has(href), `${page.slug} links to ${href}`)
    }
  }
})

test('the Markdown renderer handles headings, lists, tips, images and links', async () => {
  const { default: Markdown } = await loadJsx('src/manual/markdown.jsx')
  const router = createMemoryRouter([{ path: '*', element: React.createElement(Markdown, { text: '## Setting up\nFirst line\nsame paragraph with **bold** and *emphasis*.\n\n- one\n- [two](/manual/x)\n\n1. first\n2. second\n\n> **Tip:** a tip\n\n![A plan](/landing/plan.jpg)\n\nSee [ICO](https://ico.org.uk).' }) }])
  const html = renderToStaticMarkup(React.createElement(RouterProvider, { router }))
  assert.match(html, /<h2 id="setting-up">Setting up<\/h2>/)
  assert.match(html, /<p>First line same paragraph with <strong>bold<\/strong> and <em>emphasis<\/em>\.<\/p>/)
  assert.match(html, /<ul><li>one<\/li><li><a href="\/manual\/x"[^>]*>two<\/a><\/li><\/ul>/)
  assert.match(html, /<ol><li>first<\/li><li>second<\/li><\/ol>/)
  assert.match(html, /<aside class="manual-tip"><strong>Tip:<\/strong> a tip<\/aside>/)
  assert.match(html, /<img src="\/landing\/plan.jpg" alt="A plan" loading="lazy"\/>/)
  assert.match(html, /<a href="https:\/\/ico.org.uk" target="_blank" rel="noreferrer">ICO<\/a>/)
})

test('the manual shows its contents, a page with previous and next links, and searches', async () => {
  const contents = await render('/manual')
  assert.match(contents, /TapLine IDP manual/)
  assert.match(contents, /href="\/manual\/priorities-and-plans"/)
  const page = await render('/manual/assessing-players')
  assert.match(page, /<h1>Assessing players<\/h1>/)
  assert.match(page, /aria-current="page"[^>]*>Assessing players</)
  assert.match(page, /← Players and periods/)
  assert.match(page, /The skill matrix →/)
  const { searchPages } = await loadJsx('src/manual/content.js')
  const hits = searchPages('revoke link')
  assert.ok(hits.some(h => h.slug === 'self-assessment') && hits.some(h => h.slug === 'reports'))
  assert.deepEqual(searchPages('xyzzy'), [])
})
