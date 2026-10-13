import { defineConfig } from 'vite'
import { sharedBuild, sharedPlugins, sharedServer } from './vite.shared.mjs'

export default defineConfig({
  plugins: sharedPlugins(),
  server: {
    ...sharedServer,
    port: 5173
  },
  build: sharedBuild
})
