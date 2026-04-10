import { defineNuxtConfig } from 'nuxt/config'

export default defineNuxtConfig({
  imports: {
    dirs: [
      'composables/**',
      'types/**',
    ],
    autoImport: true
  },
  components: [
    { path: './components', pathPrefix: false }
  ]
})
