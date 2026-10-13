import vue from '@vitejs/plugin-vue'
import AutoImport from 'unplugin-auto-import/vite'
import Components from 'unplugin-vue-components/vite'
import { ElementPlusResolver } from 'unplugin-vue-components/resolvers'

const elementPlusResolver = ElementPlusResolver({ importStyle: 'css' })

export function sharedPlugins() {
  return [
    vue(),
    AutoImport({ resolvers: [elementPlusResolver] }),
    Components({ resolvers: [elementPlusResolver] })
  ]
}

export const sharedServer = {
  host: '127.0.0.1'
}

export const sharedBuild = {
  rollupOptions: {
    output: {
      manualChunks(id) {
        if (!id.includes('node_modules')) return
        if (id.includes('element-plus') || id.includes('@element-plus')) return 'element-plus'
        if (id.includes('/vue/') || id.includes('\\vue\\') || id.includes('vue-router') || id.includes('@vue')) return 'vue'
      }
    }
  }
}
