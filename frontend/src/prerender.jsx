/* eslint-disable react-refresh/only-export-components -- a build-time entry, never hot-reloaded */
// Server-side entry used only at build time: renders each public page to HTML (see scripts/prerender.mjs).
import { renderToString } from 'react-dom/server'
import { Route, Routes, StaticRouter } from 'react-router'
import LegalPage from './legal/LegalPage'
import ManualPage from './manual/ManualPage'
import Landing from './site/Landing'
export { PUBLIC_ROUTES } from './site/routes'

// The same pages and props as App.jsx renders before the session check finishes (user undefined).
export function render(path) {
  return renderToString(<StaticRouter location={path}><Routes>
    <Route path="/" element={<Landing />} />
    <Route path="/manual" element={<ManualPage />} />
    <Route path="/manual/:slug" element={<ManualPage />} />
    <Route path="/privacy" element={<LegalPage page="privacy" />} />
    <Route path="/privacy/players" element={<LegalPage page="players" />} />
    <Route path="/terms" element={<LegalPage page="terms" />} />
  </Routes></StaticRouter>)
}
