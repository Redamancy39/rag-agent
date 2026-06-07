import { createServer } from 'vite'
import vue from '@vitejs/plugin-vue'

const portIndex = process.argv.findIndex((arg) => arg === '--port')
const portArg = portIndex >= 0 ? process.argv[portIndex + 1] : undefined
const port = Number(process.env.PORT || portArg) || 5173

const server = await createServer({
  configFile: false,
  root: process.cwd(),
  plugins: [vue()],
  server: {
    host: '127.0.0.1',
    port
  }
})

await server.listen()
server.printUrls()
