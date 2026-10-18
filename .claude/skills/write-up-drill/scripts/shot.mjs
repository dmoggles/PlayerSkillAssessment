// A full-page PNG of a review sheet, for looking at it yourself before sending it.
// Needs playwright-core in PW_DIR (install once: npm install --prefix "$PW_DIR" playwright-core) and a Chromium
// (npx --prefix "$PW_DIR" playwright-core install chromium, if ~/.cache/ms-playwright has none).
//   PW_DIR=<scratch>/pw node .claude/skills/write-up-drill/scripts/shot.mjs OUT.html OUT.png
import fs from 'node:fs'
import os from 'node:os'
import path from 'node:path'

const [html, png] = process.argv.slice(2)
const dir = process.env.PW_DIR
if (!html || !png || !dir) { console.error('usage: PW_DIR=... shot.mjs SHEET.html OUT.png'); process.exit(2) }
const { chromium } = await import(path.join(dir, 'node_modules/playwright-core/index.mjs'))
const cache = path.join(os.homedir(), '.cache/ms-playwright')
const build = fs.existsSync(cache) ? fs.readdirSync(cache).filter(n => n.startsWith('chromium-')).sort().pop() : null
const executablePath = build ? path.join(cache, build, 'chrome-linux64/chrome') : undefined
const browser = await chromium.launch(executablePath && fs.existsSync(executablePath) ? { executablePath } : {})
const page = await browser.newPage({ viewport: { width: 1300, height: 800 } })
await page.goto('file://' + path.resolve(html))
await page.screenshot({ path: png, fullPage: true })
await browser.close()
console.log(`wrote ${png}`)
