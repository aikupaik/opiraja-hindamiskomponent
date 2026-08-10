import { useEffect, useMemo, useState } from 'react'
import { api, errorMessage, type KstConfiguration, type KstConfigurationHistory } from './api'

const initialConfiguration: KstConfiguration = {
  feedback_credible_mass: 0.9,
  reliability_floor: { maximum: 10, minimum: 7, multiplier: 1.5 },
  safety_cap: { minimum_above_floor: 1, node_multiplier: 2 },
  schema_version: 1,
  stop_confidence: 0.8,
}

type Props = { maxGraphNodes: number }

export function KstParametersPage({ maxGraphNodes }: Props) {
  const [history, setHistory] = useState<KstConfigurationHistory | null>(null)
  const [draft, setDraft] = useState<KstConfiguration>(initialConfiguration)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [activating, setActivating] = useState<string | null>(null)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')

  async function refresh() {
    setLoading(true)
    try {
      const next = await api<KstConfigurationHistory>('/api/v1/admin/kst-configurations')
      setHistory(next)
      const active = next.versions.find((version) => version.is_active)
      if (active) setDraft(active.configuration)
    } catch (caught) {
      setError(errorMessage(caught))
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { void refresh() }, [])

  const preview = useMemo(() => {
    const values: { nodes: number; floor: number; cap: number }[] = []
    for (let nodes = 1; nodes <= maxGraphNodes; nodes += 1) {
      const floor = Math.min(
        Math.max(draft.reliability_floor.minimum, Math.ceil(draft.reliability_floor.multiplier * nodes)),
        draft.reliability_floor.maximum,
      )
      values.push({
        nodes,
        floor,
        cap: Math.ceil(Math.max(draft.safety_cap.node_multiplier * nodes, floor + draft.safety_cap.minimum_above_floor)),
      })
    }
    return values
  }, [draft, maxGraphNodes])

  function number(path: 'feedback_credible_mass' | 'stop_confidence' | 'floor-minimum' | 'floor-multiplier' | 'floor-maximum' | 'cap-minimum' | 'cap-multiplier', value: string) {
    const parsed = Number(value)
    if (!Number.isFinite(parsed)) return
    setDraft((current) => {
      if (path === 'feedback_credible_mass' || path === 'stop_confidence') return { ...current, [path]: parsed }
      if (path === 'floor-minimum' || path === 'floor-multiplier' || path === 'floor-maximum') {
        const key = path === 'floor-minimum' ? 'minimum' : path === 'floor-maximum' ? 'maximum' : 'multiplier'
        return { ...current, reliability_floor: { ...current.reliability_floor, [key]: parsed } }
      }
      const key = path === 'cap-minimum' ? 'minimum_above_floor' : 'node_multiplier'
      return { ...current, safety_cap: { ...current.safety_cap, [key]: parsed } }
    })
  }

  async function save() {
    setError('')
    setNotice('')
    setSaving(true)
    try {
      await api('/api/v1/admin/kst-configurations', { method: 'POST', json: draft })
      setNotice('Mustand on salvestatud. See jõustub aktiveerimisel.')
      await refresh()
    } catch (caught) { setError(errorMessage(caught)) } finally { setSaving(false) }
  }

  async function activate(id: string) {
    if (!window.confirm('Kas aktiveerida see seadistus? See mõjutab ainult pärast aktiveerimist loodud teste.')) return
    setError('')
    setNotice('')
    setActivating(id)
    try {
      await api(`/api/v1/admin/kst-configurations/${encodeURIComponent(id)}/activate`, { method: 'POST' })
      setNotice('Seadistus on aktiveeritud. Olemasolevad testid ei muutu.')
      await refresh()
    } catch (caught) { setError(errorMessage(caught)) } finally { setActivating(null) }
  }

  return (
    <main className="page">
      <div className="page-heading">
        <div><p className="eyebrow">Käitusseaded</p><h1>KST parameetrid</h1></div>
      </div>
      {error && <div className="notice error">{error}</div>}
      {notice && <div className="notice success">{notice}</div>}
      {loading && <div className="panel" style={{ padding: 24 }}>Laadin seadistuste ajalugu…</div>}
      {!loading && <div className="form-grid">
        <section className="panel" style={{ padding: 27 }}>
          <div className="panel-title"><div><h2>Mustandi muutmine</h2></div></div>
          <div className="field-row">
            <label><span>Peatumise usaldus</span><input type="number" min="0.0001" max="1" step="0.01" value={draft.stop_confidence} onChange={(event) => number('stop_confidence', event.target.value)} /></label>
            <label><span>Tagasiside usaldusväärne mass</span><input type="number" min="0.0001" max="1" step="0.01" value={draft.feedback_credible_mass} onChange={(event) => number('feedback_credible_mass', event.target.value)} /></label>
          </div>
          <h3>Usaldusväärsuse alampiir</h3>
          <div className="field-row">
            <label><span>Minimum</span><input type="number" min="0" step="1" value={draft.reliability_floor.minimum} onChange={(event) => number('floor-minimum', event.target.value)} /></label>
            <label><span>Multiplier</span><input type="number" min="0.0001" step="0.1" value={draft.reliability_floor.multiplier} onChange={(event) => number('floor-multiplier', event.target.value)} /></label>
            <label><span>Maximum</span><input type="number" min="0" step="1" value={draft.reliability_floor.maximum} onChange={(event) => number('floor-maximum', event.target.value)} /></label>
          </div>
          <h3>Turvapiir</h3>
          <div className="field-row">
            <label><span>Miinimum üle alampiiri</span><input type="number" min="0" step="1" value={draft.safety_cap.minimum_above_floor} onChange={(event) => number('cap-minimum', event.target.value)} /></label>
            <label><span>Sõlme kordaja</span><input type="number" min="0.0001" step="0.1" value={draft.safety_cap.node_multiplier} onChange={(event) => number('cap-multiplier', event.target.value)} /></label>
          </div>
          <button className="primary" disabled={saving} onClick={() => void save()}>{saving ? 'Salvestan…' : 'Salvesta mustand'}</button>
        </section>
        <section className="panel" style={{ padding: 27 }}>
          <div className="panel-title"><div><h2>Arvutatud piirid</h2></div></div>
          <table><thead><tr><th>Sõlmi</th><th>Usaldusväärsuse alampiir</th><th>Turvapiir</th></tr></thead><tbody>{preview.map((row) => <tr key={row.nodes}><td>{row.nodes}</td><td>{row.floor}</td><td>{row.cap}</td></tr>)}</tbody></table>
        </section>
      </div>}
      {!loading && history && <section className="panel" style={{ padding: 27 }}>
        <div className="panel-title"><div><h2>Versioonide ajalugu</h2></div></div>
        {history.versions.map((version) => <article key={version.id} style={{ display: 'flex', justifyContent: 'space-between', gap: 20, padding: '18px 0', borderBottom: '1px solid var(--line)' }}>
          <div><strong>{version.is_active ? 'Aktiivne versioon' : 'Ajalooline versioon'}</strong><p className="mono">{version.configuration_hash}</p><small>Looja: {version.created_by} · {new Date(version.created_at).toLocaleString()}</small>{version.last_activated_at && <small> · Aktiveerija: {version.last_activated_by} · {new Date(version.last_activated_at).toLocaleString()}</small>}</div>
          {!version.is_active && <button className="secondary" disabled={activating !== null} onClick={() => void activate(version.id)}>{activating === version.id ? 'Aktiveerin…' : 'Taasta aktiivseks'}</button>}
        </article>)}
      </section>}
    </main>
  )
}
