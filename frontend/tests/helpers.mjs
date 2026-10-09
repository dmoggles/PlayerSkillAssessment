import { createServer } from 'vite'

// Loads a JSX module through Vite, so tests can render components without a build.
export async function loadJsx(entry) {
  const server = await createServer({ logLevel: 'silent', server: { middlewareMode: true, hmr: false }, appType: 'custom' })
  try { return await server.ssrLoadModule(`/${entry}`) }
  finally { await server.close() }
}
