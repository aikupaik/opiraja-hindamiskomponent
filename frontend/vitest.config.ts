import react from '@vitejs/plugin-react'
import { defineConfig } from 'vitest/config'

export default defineConfig({
  plugins: [react()],
  test: {
    environment: 'jsdom',
    environmentOptions: {
      jsdom: { url: 'http://localhost/test/00000000-0000-4000-8000-000000000001' },
    },
    setupFiles: ['./src/test/setup.ts'],
    restoreMocks: true,
  },
})
