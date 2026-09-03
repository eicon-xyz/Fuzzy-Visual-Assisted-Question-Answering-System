import { defineConfig, externalizeDepsPlugin } from 'electron-vite'
import vue from '@vitejs/plugin-vue'
import { resolve } from 'node:path'

export default defineConfig({
  main: {
    plugins: [externalizeDepsPlugin()],
    build: {
      rollupOptions: {
        // electron 在 devDependencies，externalizeDepsPlugin 不覆盖它；
        // 不显式 external 会把 npm stub（getElectronPath）打进产物
        external: ['electron'],
        input: { main: resolve(__dirname, 'electron/main.ts') }
      }
    }
  },
  preload: {
    plugins: [externalizeDepsPlugin()],
    build: {
      rollupOptions: {
        external: ['electron'],
        input: { preload: resolve(__dirname, 'electron/preload.ts') }
      }
    }
  },
  renderer: {
    root: resolve(__dirname),
    build: {
      rollupOptions: {
        input: { index: resolve(__dirname, 'index.html') }
      }
    },
    plugins: [vue()]
  }
})
