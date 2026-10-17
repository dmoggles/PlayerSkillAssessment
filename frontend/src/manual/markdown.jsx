import { Fragment } from 'react'
import { Link } from 'react-router-dom'

// A small Markdown renderer for the manual, which is written by us: ## and ### headings, paragraphs, - and 1. lists,
// > tips, images on their own line, and **bold**, *italic*, `code` and [links]. Links to our own pages use the
// router; others open in a new tab.
const headingId = text => text.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '')

const INLINE = /(\*\*[^*]+\*\*|\*[^*]+\*|`[^`]+`|\[[^\]]+\]\([^)]+\))/g

function inline(text) {
  return text.split(INLINE).filter(Boolean).map((part, i) => {
    if (part.startsWith('**')) return <strong key={i}>{inline(part.slice(2, -2))}</strong>
    if (part.startsWith('`')) return <code key={i}>{part.slice(1, -1)}</code>
    if (part.startsWith('*')) return <em key={i}>{inline(part.slice(1, -1))}</em>
    const link = part.match(/^\[([^\]]+)\]\(([^)]+)\)$/)
    if (link) {
      const [, label, href] = link
      return href.startsWith('/') ? <Link key={i} to={href}>{inline(label)}</Link> : <a key={i} href={href} target="_blank" rel="noreferrer">{inline(label)}</a>
    }
    return <Fragment key={i}>{part}</Fragment>
  })
}

function parseBlocks(text) {
  const blocks = []
  for (const line of text.split('\n')) {
    const last = blocks[blocks.length - 1]
    const trimmed = line.trim()
    let m
    if (!trimmed) { if (last) last.closed = true; continue }
    if ((m = trimmed.match(/^(#{2,3})\s+(.*)$/))) blocks.push({ type: `h${m[1].length}`, text: m[2], closed: true })
    else if ((m = trimmed.match(/^!\[([^\]]*)\]\(([^)]+)\)$/))) blocks.push({ type: 'image', alt: m[1], src: m[2], closed: true })
    else if ((m = trimmed.match(/^(-|\d+\.)\s+(.*)$/))) {
      const type = m[1] === '-' ? 'ul' : 'ol'
      if (last?.type === type && !last.closed) last.items.push(m[2])
      else blocks.push({ type, items: [m[2]] })
    } else if ((m = trimmed.match(/^>\s?(.*)$/))) {
      if (last?.type === 'tip' && !last.closed) last.text += ` ${m[1]}`
      else blocks.push({ type: 'tip', text: m[1] })
    } else if ((last?.type === 'ul' || last?.type === 'ol') && !last.closed && /^\s+/.test(line)) last.items[last.items.length - 1] += ` ${trimmed}`
    else if (last?.type === 'p' && !last.closed) last.text += ` ${trimmed}`
    else blocks.push({ type: 'p', text: trimmed })
  }
  return blocks
}

export default function Markdown({ text }) {
  return parseBlocks(text).map((block, i) => {
    switch (block.type) {
      case 'h2': return <h2 key={i} id={headingId(block.text)}>{inline(block.text)}</h2>
      case 'h3': return <h3 key={i} id={headingId(block.text)}>{inline(block.text)}</h3>
      case 'ul': return <ul key={i}>{block.items.map((item, j) => <li key={j}>{inline(item)}</li>)}</ul>
      case 'ol': return <ol key={i}>{block.items.map((item, j) => <li key={j}>{inline(item)}</li>)}</ol>
      case 'tip': return <aside key={i} className="manual-tip">{inline(block.text)}</aside>
      case 'image': return <figure key={i} className="manual-figure"><img src={block.src} alt={block.alt} loading="lazy" /><figcaption>{block.alt}</figcaption></figure>
      default: return <p key={i}>{inline(block.text)}</p>
    }
  })
}
