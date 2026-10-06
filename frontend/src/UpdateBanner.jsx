import { useEffect, useState } from 'react'
import { getServerVersion } from './api'
import { APP_VERSION, isOutdated } from './version'

const CHECK_EVERY_MS = 5 * 60 * 1000

// After a deploy, an open tab keeps running the old app against the new server. Check the server's version
// now and then (and when the tab comes back into view) and offer a reload; never reload by itself, so
// unsaved work is not lost.
export default function UpdateBanner() {
  const [outdated, setOutdated] = useState(false)
  useEffect(() => {
    if (APP_VERSION === 'local') return
    let live = true
    const check = () => getServerVersion().then(version => { if (live && isOutdated(APP_VERSION, version)) setOutdated(true) }).catch(() => {})
    const onVisible = () => { if (document.visibilityState === 'visible') check() }
    const timer = setInterval(check, CHECK_EVERY_MS)
    document.addEventListener('visibilitychange', onVisible)
    return () => { live = false; clearInterval(timer); document.removeEventListener('visibilitychange', onVisible) }
  }, [])
  if (!outdated) return null
  return <div className="update-banner" role="status">
    <span>A new version of the app is available. Save any changes, then reload.</span>
    <button type="button" onClick={() => window.location.reload()}>Reload</button>
  </div>
}
