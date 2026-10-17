import { APP_NAME } from '../brand'
import { PAGES } from '../manual/content'

// The public pages that are prerendered to static HTML, with what search engines and link previews show for each.
export const SITE_DESCRIPTION = `${APP_NAME} helps grassroots football coaches assess each player's skills, agree what they should work on next, and give them a plan with drills.`

export const PUBLIC_ROUTES = [
  { path: '/', title: `${APP_NAME}: individual development plans for grassroots football`, description: SITE_DESCRIPTION },
  { path: '/manual', title: `Manual · ${APP_NAME}`, description: `How to use ${APP_NAME}: assess your players, choose what they work on, and give them a plan.` },
  ...PAGES.map(page => ({ path: `/manual/${page.slug}`, title: `${page.title} · ${APP_NAME}`, description: page.summary })),
  { path: '/privacy', title: `Privacy notice · ${APP_NAME}`, description: `How ${APP_NAME} looks after coaches' and players' information.` },
  { path: '/privacy/players', title: `For players and parents · ${APP_NAME}`, description: `What ${APP_NAME} keeps about players, who can see it, and how to have it changed or deleted.` },
  { path: '/terms', title: `Terms of use · ${APP_NAME}`, description: `The terms for using ${APP_NAME}, including how we process players' information for clubs.` },
]
