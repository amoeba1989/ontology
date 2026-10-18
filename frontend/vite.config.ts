import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import { fileURLToPath, URL } from 'node:url'
import { execFileSync } from 'node:child_process'
import { existsSync, readFileSync } from 'node:fs'

const revisionFile = fileURLToPath(new URL('../.deployment-revision', import.meta.url))
const revision = process.env.GITHUB_SHA || (existsSync(revisionFile) ? readFileSync(revisionFile, 'utf8').trim() : (() => {
  try { return execFileSync('git', ['rev-parse', 'HEAD'], { encoding: 'utf8' }).trim() }
  catch { return 'unknown' }
})())
const builtAt = new Date().toISOString().replace('T', ' ').slice(0, 16) + ' UTC'
const version = readFileSync(fileURLToPath(new URL('../VERSION', import.meta.url)), 'utf8').trim()
if (!/^\d+\.\d+\.\d+$/.test(version)) throw new Error('Invalid product VERSION')
const buildInfo = `v${version} · ${builtAt} · ${revision.slice(0, 7)}`

// https://vite.dev/config/
export default defineConfig({
  define: { __APP_BUILD_INFO__: JSON.stringify(buildInfo) },
  plugins: [vue()],
  optimizeDeps: { include: ['dagre', 'marked'] },
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url)),
    },
  },
  server: {
    host: '0.0.0.0',
    port: Number(process.env.FRONTEND_PORT || 5177),
    allowedHosts: ['ontology.ojlab.com'],
    proxy: {
      '/api': {
        target: process.env.VITE_PROXY_TARGET || 'http://127.0.0.1:8001',
        changeOrigin: true,
      },
    },
  },
})
