import { defineConfig } from 'vitest/config'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [
    react(),
    tailwindcss(),
  ],
  server: {
    host: '0.0.0.0',
    port: 5173,
    strictPort: true,
  },
  test: {
    environment: 'jsdom',
    setupFiles: ['./src/test/setup.ts'],
    exclude: [
      '**/node_modules/**',
      '**/dist/**',
      'src/utils/performanceSummary.test.mjs',
    ],
  },
  build: {
    rollupOptions: {
      output: {
        manualChunks(id: string) {
          const normalizedId = id.replaceAll('\\', '/');
          if (normalizedId.includes('/node_modules/framer-motion/'))
            return 'animation';
          if (normalizedId.includes('/node_modules/socket.io'))
            return 'socket';
        },
      },
    },
  },
})
