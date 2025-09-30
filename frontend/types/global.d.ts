import type { ConfirmOptions } from './common'

declare module '#app' {
  interface NuxtApp {
    $confirm: (options: ConfirmOptions | string) => Promise<boolean>
  }
}

declare module 'vue' {
  interface ComponentCustomProperties {
    $confirm: (options: ConfirmOptions | string) => Promise<boolean>
  }
}

export {} 