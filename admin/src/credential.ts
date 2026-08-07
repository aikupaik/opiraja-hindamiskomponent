import type { CredentialSource } from '@opiraja/frontend-api'

export const ADMIN_CREDENTIAL_STORAGE_KEY = 'assessment-admin-jwt'

const expiredListeners = new Set<() => void>()

export const adminCredentialSource: CredentialSource = {
  getCredential: () => sessionStorage.getItem(ADMIN_CREDENTIAL_STORAGE_KEY),
}

export function storeAdminCredential(credential: string): void {
  sessionStorage.setItem(ADMIN_CREDENTIAL_STORAGE_KEY, credential)
}

export function clearAdminCredential(): void {
  sessionStorage.removeItem(ADMIN_CREDENTIAL_STORAGE_KEY)
}

export function expireAdminCredential(): void {
  clearAdminCredential()
  for (const listener of expiredListeners) listener()
}

export function subscribeToAdminCredentialExpiry(
  listener: () => void,
): () => void {
  expiredListeners.add(listener)
  return () => expiredListeners.delete(listener)
}
