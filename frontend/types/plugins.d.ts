import type { ConfirmOptions } from '~/types/common'

type ConfirmInput = ConfirmOptions | string

declare module '#app' {
  interface NuxtApp {
    $confirm: (options: ConfirmInput) => Promise<boolean>
  }
}

declare module 'nuxt/app' {
  interface NuxtApp {
    $confirm: (options: ConfirmInput) => Promise<boolean>
  }
}

declare module '@vue/runtime-core' {
  interface ComponentCustomProperties {
    $confirm: (options: ConfirmInput) => Promise<boolean>
  }
}

export {}
