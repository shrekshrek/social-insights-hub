import { defineNuxtConfig } from 'nuxt/config'

export default defineNuxtConfig({
  imports: {
    dirs: ['composables/**', 'stores/**', 'types/**'],
    autoImport: true
  },
  components: [
    { path: './components', pathPrefix: false }
  ]
})
