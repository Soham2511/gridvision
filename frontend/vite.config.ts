import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

const frontendNodeModules = new URL('./node_modules/', import.meta.url).pathname
  .replace(/^\/([A-Za-z]:\/)/, '$1')

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: [
      { find: /^react$/, replacement: `${frontendNodeModules}react` },
      { find: /^react\/(.*)$/, replacement: `${frontendNodeModules}react/$1` },
      { find: /^react-markdown$/, replacement: `${frontendNodeModules}react-markdown` },
      { find: /^remark-gfm$/, replacement: `${frontendNodeModules}remark-gfm` },
      { find: /^recharts$/, replacement: `${frontendNodeModules}recharts` },
      { find: /^lucide-react$/, replacement: `${frontendNodeModules}lucide-react` },
    ],
  },
})
