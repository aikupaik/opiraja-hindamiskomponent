import type { CredentialSource } from '@opiraja/frontend-api'
import { parseTestPath } from './path'

export type { CredentialSource }

const expiredListeners = new Set<() => void>()

const STORAGE_PREFIX = 'assessment-player-jwt:'

function storageKey(testId: string): string {
  return `${STORAGE_PREFIX}${testId}`
}

function currentTestId(): string | null {
  return parseTestPath(window.location.pathname)
}

export const playerCredentialSource: CredentialSource = {
  getCredential: () => {
    const testId = currentTestId()
    return testId === null ? null : sessionStorage.getItem(storageKey(testId))
  },
}

export function expirePlayerCredential(): void {
  const testId = currentTestId()
  if (testId !== null) sessionStorage.removeItem(storageKey(testId))
  for (const listener of expiredListeners) listener()
}

export function bootstrapPlayerCredential(testId: string): void {
  const match = /^#token=(.+)$/.exec(window.location.hash)
  if (match === null) return
  sessionStorage.setItem(storageKey(testId), match[1])
  window.history.replaceState(
    window.history.state,
    '',
    `${window.location.pathname}${window.location.search}`,
  )
}

export function playerCredentialStorageKey(testId: string): string {
  return storageKey(testId)
}

export function subscribeToPlayerCredentialExpiry(
  listener: () => void,
): () => void {
  expiredListeners.add(listener)
  return () => expiredListeners.delete(listener)
}
