// Set at image build time (release tag, dev-<sha>, or git describe locally).
export const APP_VERSION = import.meta.env.VITE_APP_VERSION || 'local'
