import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [
    react(),
    tailwindcss(),
  ],
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
