// The manual's pages: Markdown files in ./pages, ordered by their number prefix. Each starts with a small header:
// ---
// title: Getting started
// summary: One line for the contents list.
// ---
const files = import.meta.glob('./pages/*.md', { query: '?raw', import: 'default', eager: true })

export function parsePage(path, text) {
  const match = text.match(/^---\n([\s\S]*?)\n---\n?([\s\S]*)$/)
  const meta = Object.fromEntries((match?.[1] ?? '').split('\n').map(line => line.split(/:\s*(.*)/s).slice(0, 2)).filter(([key]) => key))
  const slug = path.split('/').pop().replace(/\.md$/, '').replace(/^\d+-/, '')
  return { slug, title: meta.title ?? slug, summary: meta.summary ?? '', body: (match?.[2] ?? text).trim() }
}

export const PAGES = Object.keys(files).sort().map(path => parsePage(path, files[path]))

// Pages whose title or text contains every word of the query, with a snippet around the first match.
export function searchPages(query, pages = PAGES) {
  const words = query.toLowerCase().split(/\s+/).filter(Boolean)
  if (!words.length) return []
  return pages.flatMap(page => {
    const plain = page.body.replace(/^\s*(-|\d+\.)\s+/gm, '').replace(/!\[[^\]]*\]\([^)]*\)/g, '').replace(/\[([^\]]*)\]\([^)]*\)/g, '$1').replace(/[*#>`_]/g, '').replace(/\s+/g, ' ')
    const haystack = `${page.title} ${plain}`.toLowerCase()
    if (!words.every(word => haystack.includes(word))) return []
    const at = plain.toLowerCase().indexOf(words[0])
    const snippet = at < 0 ? page.summary : `${at > 60 ? '…' : ''}${plain.slice(Math.max(0, at - 60), at + 120).trim()}…`
    return [{ ...page, snippet }]
  })
}
