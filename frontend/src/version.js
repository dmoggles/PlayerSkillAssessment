// Set at image build time (release tag, dev-<sha>, or git describe locally).
export const APP_VERSION = import.meta.env.VITE_APP_VERSION || 'local'

// True when the server is running a different build from this page, so the page should be reloaded.
// Local builds have no real version, so they never ask.
export const isOutdated = (pageVersion, serverVersion) =>
  Boolean(serverVersion) && pageVersion !== 'local' && serverVersion !== 'local' && serverVersion !== pageVersion
