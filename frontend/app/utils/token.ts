import type { Buffer } from 'node:buffer'

/**
 * 将 JWT payload 使用的 base64url 字符串转换为标准 base64 字符串，
 * 并补齐缺失的填充符 '='，确保 atob/Buffer 可以正常解析。
 */
const normalizeBase64 = (value: string): string => {
  const paddingNeeded = (4 - (value.length % 4)) % 4
  return value.replace(/-/g, '+').replace(/_/g, '/').padEnd(value.length + paddingNeeded, '=')
}

/**
 * 在浏览器或 Node 环境中通用的 base64 解码方法：
 * - 浏览器：使用全局 atob
 * - Node：使用 Buffer.from
 */
const decodeBase64 = (value: string): string => {
  const normalized = normalizeBase64(value)

  if (typeof globalThis.atob === 'function') {
    return globalThis.atob(normalized)
  }

  const bufferCtor = (globalThis as typeof globalThis & { Buffer?: typeof Buffer }).Buffer
  if (bufferCtor) {
    return bufferCtor.from(normalized, 'base64').toString('utf-8')
  }

  return ''
}

/**
 * 解码 JWT token 的 payload 段，失败时返回 null。
 */
export const decodeJwtPayload = (token: string): Record<string, unknown> | null => {
  const parts = token.split('.')
  if (parts.length < 2) {
    return null
  }

  try {
    const payloadJson = decodeBase64(parts[1]!)
    return JSON.parse(payloadJson) as Record<string, unknown>
  } catch (error) {
    console.warn('Failed to decode JWT payload', error)
    return null
  }
}

/**
 * 判断 JWT 是否即将过期。
 *
 * @param token JWT 字符串，若为空则视为已过期。
 * @param bufferSeconds 提前多少秒视为“即将过期”，默认 30 秒。
 */
export const isJwtExpiring = (
  token: string | undefined | null,
  bufferSeconds = 30,
): boolean => {
  if (!token) {
    return true
  }

  const payload = decodeJwtPayload(token)
  const exp = typeof payload?.exp === 'number' ? (payload.exp as number) : undefined
  if (typeof exp !== 'number') {
    return false
  }

  const now = Date.now() / 1000
  return exp - bufferSeconds <= now
}
