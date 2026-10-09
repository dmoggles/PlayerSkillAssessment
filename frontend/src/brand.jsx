// The product's name and mark, in one place. The mark is TapLine's pitch strip with three rising steps.
export const APP_NAME = 'TapLine IDP'
export const PLAN_NAME = 'Individual Development Plan'

// The strip is drawn silver for dark grounds and slate for light ones; the steps stay green on both.
export function BrandMark({ tone = 'dark', size = 36 }) {
  const line = tone === 'dark' ? '#d7dde2' : '#1b2733'
  const step = tone === 'dark' ? '#85f13f' : '#3f9a14'
  return <svg className="brand-mark" width={size * 0.5} height={size} viewBox="0 0 64 128" aria-hidden="true" focusable="false">
    <g fill="none" stroke={line} strokeWidth="4" strokeLinejoin="round">
      <rect x="4" y="4" width="56" height="120" rx="1" />
      <path d="M4 30H60M4 98H60" />
      <path d="M60 15a11 11 0 0 1-11-11M60 113a11 11 0 0 0-11 11" />
    </g>
    <g fill={step}>
      <rect x="14" y="76" width="12" height="14" rx="2" />
      <rect x="26" y="58" width="12" height="32" rx="2" opacity=".85" />
      <rect x="38" y="40" width="12" height="50" rx="2" opacity=".7" />
    </g>
  </svg>
}

// "TapLine" with the IDP tag, as in the logo.
export function Wordmark({ tone = 'dark' }) {
  return <span className={`wordmark wordmark-${tone}`}><span className="wordmark-name"><span className="wordmark-tap">Tap</span><span className="wordmark-line">Line</span></span><span className="wordmark-tag">IDP</span></span>
}

// The small brand line on pages players and parents open: the team leads, the app stays quiet.
export function MadeWith() {
  return <footer className="made-with"><BrandMark tone="light" size={22} /><span>Made with <strong>{APP_NAME}</strong></span></footer>
}
