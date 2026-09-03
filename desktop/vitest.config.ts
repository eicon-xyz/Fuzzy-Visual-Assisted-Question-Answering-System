import { defineConfig } from 'vitest/config'

export default defineConfig({
  test: {
    include: ['core/**/*.test.ts', 'tests/**/*.test.ts', 'src/**/*.test.ts'],
    environment: 'node'
  }
})
