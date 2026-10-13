import { createServer } from 'vite'
import { sharedPlugins, sharedServer } from '../vite.shared.mjs'

const portIndex = process.argv.findIndex((arg) => arg === '--port')
const portArg = portIndex >= 0 ? process.argv[portIndex + 1] : undefined
const port = Number(process.env.PORT || portArg) || 5173

const server = await createServer({
  configFile: false,
  root: process.cwd(),
  plugins: sharedPlugins(),
  server: {
    ...sharedServer,
    port
  }
})

await server.listen()
server.printUrls()
