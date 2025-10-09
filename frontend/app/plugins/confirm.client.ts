/**
 * 全局确认对话框插件
 * 
 * 基于Nuxt UI v3的useOverlay实现程序化确认对话框
 * 配合ConfirmModal组件使用，提供完整的确认/取消功能
 */

import type { ConfirmOptions } from '~/types/common'

declare global {
  interface Window {
    $confirm: (options: ConfirmOptions | string) => Promise<boolean>
  }
}

export default defineNuxtPlugin(() => {
  // 创建全局确认函数
  const confirm = async (options: ConfirmOptions | string): Promise<boolean> => {
    // 如果传入的是字符串，转换为选项对象
    const opts: ConfirmOptions = typeof options === 'string' 
      ? { message: options }
      : options

    const {
      title = '确认操作',
      message,
      confirmText = '确认',
      cancelText = '取消',
      type = 'warning'
    } = opts

    // 动态导入确认对话框组件
    const ConfirmModal = (await import('~/app/components/ConfirmModal.vue')).default
    
    // 使用Nuxt UI v3的useOverlay来程序化创建模态框
    const overlay = useOverlay()
    
    // 创建模态框实例
    const modal = overlay.create(ConfirmModal, {
      props: {
        title,
        message,
        confirmText,
        cancelText,
        type
      }
    })
    
    // 打开模态框并等待用户操作
    const instance = modal.open()
    
    // 返回用户的选择结果
    return await instance.result
  }

  // 注册到全局
  return {
    provide: {
      confirm
    }
  }
}) 
