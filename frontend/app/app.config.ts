export default defineAppConfig({
  ui: {
    // 全局颜色配置 - 这与@nuxtjs/color-mode不冲突
    colors: {
      primary: 'blue',
      secondary: 'slate',
      success: 'green',
      info: 'blue',
      warning: 'orange',
      error: 'red',
      neutral: 'gray'
    },
    // Input组件全局配置 - 确保占满宽度
    input: {
      slots: {
        root: 'w-full',
        base: 'w-full'
      }
    },
    // FormField组件配置 - 减少间距
    formField: {
      slots: {
        root: 'space-y-2'
      }
    },
    // Dropdown组件配置 - 确保正确渲染
    dropdown: {
      slots: {
        root: 'relative inline-block text-left'
      }
    }
  }
}) 