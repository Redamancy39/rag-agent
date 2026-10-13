import { build } from 'vite'
import { mkdir, rm, writeFile } from 'node:fs/promises'
import { join } from 'node:path'
import { sharedBuild, sharedPlugins } from '../vite.shared.mjs'

const baseConfig = {
  configFile: false,
  root: process.cwd(),
  plugins: sharedPlugins()
}

async function buildTo(outDir, emptyOutDir) {
  await build({
    ...baseConfig,
    build: {
      ...sharedBuild,
      outDir,
      emptyOutDir
    }
  })
}

async function canWriteDistAssets() {
  const assetsDir = join(process.cwd(), 'dist', 'assets')
  const probeFile = join(assetsDir, '.write-test')
  try {
    await mkdir(assetsDir, { recursive: true })
    await writeFile(probeFile, 'ok')
    await rm(probeFile, { force: true })
    return true
  } catch {
    return false
  }
}

try {
  if (await canWriteDistAssets()) {
    await buildTo('dist', true)
  } else {
    console.warn('[build] frontend/dist is locked or not writable; writing fallback output to frontend/dist-next.')
    await buildTo('dist-next', true)
  }
} catch (error) {
  if (error?.code !== 'EPERM') throw error
  console.warn('[build] frontend/dist is locked or not writable; writing fallback output to frontend/dist-next.')
  await buildTo('dist-next', true)
}
