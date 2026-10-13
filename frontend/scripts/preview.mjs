import { access } from 'node:fs/promises'
import { join } from 'node:path'
import { preview } from 'vite'
import { sharedServer } from '../vite.shared.mjs'

const portIndex = process.argv.findIndex((arg) => arg === '--port')
const portArg = portIndex >= 0 ? process.argv[portIndex + 1] : undefined
const port = Number(process.env.PORT || portArg) || 4173

async function pathExists(path) {
  try {
    await access(path)
    return true
  } catch {
    return false
  }
}

const outDir = (await pathExists(join(process.cwd(), 'dist-next'))) ? 'dist-next' : 'dist'

const server = await preview({
  configFile: false,
  root: process.cwd(),
  preview: {
    ...sharedServer,
    port
  },
  build: { outDir }
})

console.log(`[preview] serving ${outDir}`)
server.printUrls()
