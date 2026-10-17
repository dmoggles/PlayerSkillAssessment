import { createElement, lazy } from 'react'

// Pages loaded on first use. A public page arrives prerendered (see scripts/prerender.mjs); loading its code before
// React first renders lets React swap the static HTML for the live page without a "Loading…" flash.
function preloadable(load) {
  let loaded = null
  const Lazy = lazy(() => load().then(module => { loaded = module.default; return module }))
  const Page = props => createElement(loaded ?? Lazy, props)
  Page.preload = () => load().then(module => { loaded = module.default })
  return Page
}

export const LegalPage = preloadable(() => import('../legal/LegalPage'))
export const ManualPage = preloadable(() => import('../manual/ManualPage'))

export function preloadPage(pathname) {
  if (pathname === '/manual' || pathname.startsWith('/manual/')) return ManualPage.preload()
  if (pathname === '/privacy' || pathname.startsWith('/privacy/') || pathname === '/terms') return LegalPage.preload()
  return Promise.resolve()
}
