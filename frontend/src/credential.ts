import type { CredentialSource } from '@opiraja/frontend-api'

export type { CredentialSource }

const expiredListeners = new Set<() => void>()

export const permissiveCredentialSource: CredentialSource = {
  getCredential: () => null,
}

export function expirePlayerCredential(): void {
  for (const listener of expiredListeners) listener()
}

export function subscribeToPlayerCredentialExpiry(
  listener: () => void,
): () => void {
  expiredListeners.add(listener)
  return () => expiredListeners.delete(listener)
}
