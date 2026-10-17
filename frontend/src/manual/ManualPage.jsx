import { useEffect, useState } from 'react'
import { Link, Navigate, useNavigate, useParams } from 'react-router-dom'
import { APP_NAME } from '../brand'
import PublicLayout from '../site/PublicLayout'
import { PAGES, searchPages } from './content'
import Markdown from './markdown'
import './manual.css'

// The public manual: a contents page at /manual, and one page per topic at /manual/:slug, with search.
export default function ManualPage({ user }) {
  const { slug } = useParams()
  // Keyed by page, so the search box clears when you open another page.
  return <ManualView key={slug ?? ''} slug={slug} user={user} />
}

function ManualView({ slug, user }) {
  const index = PAGES.findIndex(p => p.slug === slug)
  const page = PAGES[index]
  const navigate = useNavigate()
  const [query, setQuery] = useState('')
  const results = searchPages(query)
  useEffect(() => { document.title = `${page ? page.title : 'Manual'} · ${APP_NAME}` }, [page])
  useEffect(() => { window.scrollTo(0, 0) }, [])
  if (slug && !page) return <Navigate to="/manual" replace />

  return <PublicLayout user={user}>
    <div className="manual">
      <aside className="manual-side">
        <label className="manual-search"><span className="visually-hidden">Search the manual</span>
          <input type="search" placeholder="Search the manual" value={query} onChange={e => setQuery(e.target.value)} /></label>
        {/* Phones get a picker instead of the list. */}
        <label className="manual-picker"><span className="visually-hidden">Go to a page</span>
          <select value={page?.slug ?? ''} onChange={e => navigate(e.target.value ? `/manual/${e.target.value}` : '/manual')}>
            <option value="">Contents</option>{PAGES.map(p => <option key={p.slug} value={p.slug}>{p.title}</option>)}
          </select></label>
        <nav aria-label="Manual contents"><ol>
          <li><Link to="/manual" className={!page ? 'active' : ''} aria-current={!page ? 'page' : undefined}>Contents</Link></li>
          {PAGES.map(p => <li key={p.slug}><Link to={`/manual/${p.slug}`} className={p === page ? 'active' : ''} aria-current={p === page ? 'page' : undefined}>{p.title}</Link></li>)}
        </ol></nav>
      </aside>
      <article className="manual-body">
        {query.trim() ? <SearchResults query={query} results={results} />
          : page ? <>
            <p className="manual-eyebrow"><Link to="/manual">Manual</Link></p>
            <h1>{page.title}</h1>
            <Markdown text={page.body} />
            <nav className="manual-pager" aria-label="Previous and next pages">
              {index > 0 ? <Link to={`/manual/${PAGES[index - 1].slug}`}>← {PAGES[index - 1].title}</Link> : <span />}
              {index < PAGES.length - 1 && <Link to={`/manual/${PAGES[index + 1].slug}`}>{PAGES[index + 1].title} →</Link>}
            </nav>
          </>
          : <>
            <h1>{APP_NAME} manual</h1>
            <p className="manual-lead">How to assess your players, choose what they work on, and give them a plan. New here? Start with <Link to="/manual/getting-started">Getting started</Link>.</p>
            <ol className="manual-contents">{PAGES.map(p => <li key={p.slug}><Link to={`/manual/${p.slug}`}><strong>{p.title}</strong><span>{p.summary}</span></Link></li>)}</ol>
          </>}
      </article>
    </div>
  </PublicLayout>
}

function SearchResults({ query, results }) {
  return <section aria-live="polite">
    <h1>Search</h1>
    {!results.length ? <p className="manual-lead">Nothing matches “{query.trim()}”.</p>
      : <ol className="manual-contents">{results.map(r => <li key={r.slug}><Link to={`/manual/${r.slug}`}><strong>{r.title}</strong><span>{r.snippet}</span></Link></li>)}</ol>}
  </section>
}
