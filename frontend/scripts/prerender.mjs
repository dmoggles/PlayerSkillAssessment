// After `vite build`: renders each public page into its own HTML file (/terms into terms.html), so search engines and link previews see the
// real content, and writes robots.txt and sitemap.xml. The plain app shell becomes app.html, which nginx serves for
// every other path (the app, players' links), so those never show the landing page first.
//
// SITE_URL is the site's address (for canonical links and previews). Only SITE_INDEXING=true lets search engines
// index the site; development builds leave it off.
import fs from 'node:fs'
import path from 'node:path'
import { pathToFileURL } from 'node:url'

const dist = path.resolve('dist')
const site = (process.env.SITE_URL || 'http://localhost:8080').replace(/\/$/, '')
const indexing = process.env.SITE_INDEXING === 'true'
const { render, PUBLIC_ROUTES } = await import(pathToFileURL(path.resolve('dist-ssr/prerender.js')).href)

const shell = fs.readFileSync(path.join(dist, 'index.html'), 'utf8')
const manifest = JSON.parse(fs.readFileSync(path.join(dist, '.vite/manifest.json'), 'utf8'))
// A page loaded on first use has its own script and styles; link them so the static page is styled from the start.
const PAGE_MODULES = { '/manual': 'src/manual/ManualPage.jsx', '/privacy': 'src/legal/LegalPage.jsx', '/terms': 'src/legal/LegalPage.jsx' }
const assets = route => {
  const key = Object.entries(PAGE_MODULES).find(([prefix]) => route.path === prefix || route.path.startsWith(`${prefix}/`))?.[1]
  const chunk = key && manifest[key]
  if (!chunk) return []
  return [`<link rel="modulepreload" crossorigin href="/${chunk.file}" />`, ...(chunk.css ?? []).map(css => `<link rel="stylesheet" crossorigin href="/${css}" />`)]
}
fs.writeFileSync(path.join(dist, 'app.html'), shell)

const escape = text => text.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;')
const head = route => [
  `<title>${escape(route.title)}</title>`,
  `<meta name="description" content="${escape(route.description)}" />`,
  `<link rel="canonical" href="${site}${route.path}" />`,
  `<meta property="og:type" content="website" />`,
  `<meta property="og:site_name" content="TapLine IDP" />`,
  `<meta property="og:title" content="${escape(route.title)}" />`,
  `<meta property="og:description" content="${escape(route.description)}" />`,
  `<meta property="og:url" content="${site}${route.path}" />`,
  `<meta property="og:image" content="${site}/og-image.png" />`,
  `<meta property="og:image:width" content="1200" />`,
  `<meta property="og:image:height" content="630" />`,
  `<meta name="twitter:card" content="summary_large_image" />`,
  ...(indexing ? [] : ['<meta name="robots" content="noindex, nofollow" />']),
  ...assets(route),
].join('\n    ')

for (const route of PUBLIC_ROUTES) {
  const html = shell
    .replace(/<title>[\s\S]*?<\/title>/, '')
    .replace(/\s*<meta name="description"[^>]*>/, '')
    .replace('</head>', `  ${head(route)}\n  </head>`)
    .replace('<div id="root"></div>', `<div id="root">${render(route.path)}</div>`)
  // /manual/reports is written as manual/reports.html, which nginx serves without a trailing-slash redirect.
  const file = route.path === '/' ? path.join(dist, 'index.html') : path.join(dist, `${route.path}.html`)
  fs.mkdirSync(path.dirname(file), { recursive: true })
  fs.writeFileSync(file, html)
}

// The app, private links and the API stay out of search results; development builds stay out entirely.
const PRIVATE = ['/app/', '/api/', '/self/', '/report/', '/practice/', '/invite/', '/verify/', '/reset/', '/sign-in']
fs.writeFileSync(path.join(dist, 'robots.txt'), indexing
  ? `User-agent: *\n${PRIVATE.map(p => `Disallow: ${p}`).join('\n')}\n\nSitemap: ${site}/sitemap.xml\n`
  : 'User-agent: *\nDisallow: /\n')
if (indexing) {
  fs.writeFileSync(path.join(dist, 'sitemap.xml'), `<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n${PUBLIC_ROUTES.map(r => `  <url><loc>${site}${r.path}</loc></url>`).join('\n')}\n</urlset>\n`)
}
fs.rmSync(path.resolve('dist-ssr'), { recursive: true, force: true })
fs.rmSync(path.join(dist, '.vite'), { recursive: true, force: true })
console.log(`Prerendered ${PUBLIC_ROUTES.length} pages for ${site}${indexing ? '' : ' (not indexed)'}`)
