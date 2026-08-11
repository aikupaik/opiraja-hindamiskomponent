import { useState } from 'react'
import type { FormEvent } from 'react'
import { Alert } from '../../shared/ui/Alert'
import { Button } from '../../shared/ui/Button'

export function UnlockScreen({ loading, error, onUnlock }: { loading: boolean; error: string; onUnlock: (key: string) => Promise<void> }) {
  const [key, setKey] = useState('')
  function submit(event: FormEvent) {
    event.preventDefault()
    if (key.trim()) void onUnlock(key)
  }
  return <main className="unlock">
    <div className="unlock-art" aria-hidden="true"><span className="orbit orbit-one" /><span className="orbit orbit-two" /><div className="unlock-monogram">OR</div></div>
    <form className="unlock-card" onSubmit={submit}>
      <p className="eyebrow">Piiratud ligipääsuga operaatorivaade</p><h1>Ava hindamislabor</h1>
      <label><span>Administraatori ligipääsuvõti</span><input type="password" autoComplete="current-password" value={key} onChange={(event) => setKey(event.target.value)} autoFocus /></label>
      {error && <Alert tone="error">{error}</Alert>}
      <Button className="unlock-submit" type="submit" disabled={loading || !key}>{loading ? 'Kontrollin…' : 'Sisene'}</Button>
    </form>
  </main>
}
