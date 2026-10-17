import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import '@fontsource-variable/manrope'
import './index.css'
import App from './App.jsx'
import { preloadPage } from './site/lazyPages'

// Public pages arrive prerendered; their code loads first so the live page replaces the static one seamlessly.
preloadPage(window.location.pathname).catch(() => {}).then(() => {
  createRoot(document.getElementById('root')).render(
    <StrictMode>
      <App />
    </StrictMode>,
  )
})
