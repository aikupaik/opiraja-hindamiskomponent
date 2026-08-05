export interface CredentialSource {
  getCredential(): string | null
}

export const permissiveCredentialSource: CredentialSource = {
  getCredential: () => null,
}
