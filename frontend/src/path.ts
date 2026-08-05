const UUID_PATTERN =
  /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i

export function parseTestPath(pathname: string): string | null {
  const match = /^\/test\/([^/]+)$/.exec(pathname)
  if (!match || !UUID_PATTERN.test(match[1])) {
    return null
  }
  return match[1].toLowerCase()
}
