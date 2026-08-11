export type JsonValue =
  | null
  | boolean
  | number
  | string
  | JsonValue[]
  | { [key: string]: JsonValue }

export type ExactRCall = {
  sequence: number
  request_id: string | null
  operation: string
  started_at: string
  completed_at: string | null
  duration_ms: number | null
  outcome: string
  status: number | null
  input: JsonValue
  output: JsonValue
}

export type ExperimentReport = {
  schema_version: '1.0'
  generated_at: string
  experiment_id: string
  test_id: string | null
  completion_state: 'completed' | 'partial'
  run_status: string
  event_count: number
  buffer_truncated: boolean
  data_quality_warnings: string[]
  research: {
    interpretation: string
    metadata: {
      nodes: string[]
      relations: { prerequisite: string; dependent: string }[]
      configuration_hash: string | null
      stop_confidence: number | null
      feedback_credible_mass: number | null
      reliability_floor: {
        minimum: number | null
        multiplier: number | null
        maximum: number | null
        derived_floor: number | null
      }
      safety_cap: {
        minimum_above_floor: number | null
        node_multiplier: number | null
        derived_cap: number | null
      }
      knowledge_state_count: number
      initial_prior: number[]
    }
    operations: ExactRCall[]
    adaptive_steps: {
      step: number
      timestamp: string
      candidate_id: string | null
      node: string | null
      beta: number | null
      eta: number | null
      response_correct: boolean | null
      approximate_response_interval_ms: number | null
      system_processing_ms: number | null
      posterior_before: number[]
      posterior_after: number[]
      highest_probability_states: {
        rank: number
        nodes: string[]
        probability: number
      }[]
      maximum_state_confidence: number | null
      shannon_entropy_bits: number | null
      normalized_entropy: number | null
      total_variation_movement: number | null
      selected_next_candidate_id: string | null
      decision: string
      r_processing_ms: number | null
    }[]
    summary: {
      response_count: number
      correct_count: number
      overall_accuracy: number | null
      per_node_accuracy: {
        node: string
        correct: number
        responses: number
        accuracy: number
      }[]
      node_path: string[]
      final_posterior: number[]
      stopping_reason: string | null
      confidence_limited: boolean | null
      credible_mass: number | null
      credible_state_count: number | null
      final_profile: {
        mastered: string[]
        ready_to_learn: string[]
        uncertain_ahead: string[]
        uncertain_prerequisite: string[]
        not_yet: string[]
        summary: string | null
        stop_reason: string | null
        best_state_confidence: number | null
        credible_mass: number | null
        credible_state_count: number | null
        confidence_limited: boolean | null
      } | null
    }
  }
  developer: {
    timeline: {
      stage: string
      started_at: string
      ended_at: string | null
      duration_ms: number | null
      outcome: string
    }[]
    last_successful_stage: string
    last_recorded_event: string
    traffic: {
      method: string
      endpoint: string
      status: number
      outcome: string
      request_count: number
      approximate_request_bytes: number
      approximate_response_bytes: number
    }[]
    api_latency: {
      count: number
      total_ms: number
      mean_ms: number | null
      median_ms: number | null
      maximum_ms: number | null
    }
    backend_time: {
      total_api_ms: number
      r_ms: number
      supabase_ms: number
      residual_application_ms: number
    }
    r_by_operation: DependencySummary[]
    supabase_by_operation: DependencySummary[]
    slowest_api_requests: SlowOperation[]
    slowest_r_calls: SlowOperation[]
    slowest_supabase_operations: SlowOperation[]
    thresholds: {
      api_request_ms: number
      dependency_call_ms: number
      preparation_ms: number
      interpretation: string
    }
  }
  exact_r_calls: ExactRCall[]
}

type DependencySummary = {
  operation: string
  count: number
  total_ms: number
  mean_ms: number
  maximum_ms: number
}

type SlowOperation = {
  category: 'api' | 'r' | 'supabase'
  operation: string
  duration_ms: number
  request_id: string | null
  sequence: number | null
  diagnostic_flag: boolean
}

export const reportStatusLabels: Record<string, string> = {
  active: 'Aktiivne',
  cancelled: 'Tühistatud',
  completed: 'Lõpetatud',
  failed: 'Ebaõnnestus',
  partial: 'Osaline',
}

export function downloadReportHtml(report: ExperimentReport) {
  download(
    buildReportHtml(report),
    reportFilename(report, 'html'),
    'text/html;charset=utf-8',
  )
}

export function downloadReportJson(report: ExperimentReport) {
  download(
    `${JSON.stringify(report, null, 2)}\n`,
    reportFilename(report, 'json'),
    'application/json;charset=utf-8',
  )
}

export function reportFilename(
  report: ExperimentReport,
  extension: 'html' | 'json',
) {
  const test = safeFilenamePart(report.test_id ?? report.experiment_id)
  const timestamp = new Date(report.generated_at)
    .toISOString()
    .replaceAll('-', '')
    .replaceAll(':', '')
    .replace(/\.\d{3}Z$/, 'Z')
  return `simulation-report-${test}-${timestamp}.${extension}`
}

export function buildReportHtml(report: ExperimentReport) {
  const summary = report.research.summary
  const metadata = report.research.metadata
  const profile = summary.final_profile
  const percent = (value: number | null) =>
    value === null ? '—' : `${(value * 100).toFixed(1)}%`
  const milliseconds = (value: number | null) =>
    value === null ? '—' : `${value.toFixed(3)} ms`
  const values = (items: string[]) =>
    items.length ? items.join(' · ') : '—'
  const rows = report.research.adaptive_steps
    .map(
      (step) => `<tr>
        <td>${step.step}</td>
        <td>${escapeHtml(formatTimestamp(step.timestamp))}</td>
        <td>${escapeHtml(step.candidate_id ?? '—')}<br><small>${escapeHtml(step.node ?? '—')}</small></td>
        <td>β ${number(step.beta)} · η ${number(step.eta)}</td>
        <td>${step.response_correct === null ? '—' : step.response_correct ? 'õige' : 'vale'}</td>
        <td>${milliseconds(step.approximate_response_interval_ms)}<br><small>õppija vastamise aeg</small></td>
        <td>${milliseconds(step.system_processing_ms)}<br><small>API töötlus</small></td>
        <td>${percent(step.maximum_state_confidence)}<div class="bar"><i style="width:${clampedPercent(step.maximum_state_confidence)}%"></i></div></td>
        <td>${number(step.shannon_entropy_bits)} bits<br><small>normalized ${number(step.normalized_entropy)}</small></td>
        <td>${number(step.total_variation_movement)}</td>
        <td>${escapeHtml(step.decision)}</td>
        <td>${milliseconds(step.r_processing_ms)}</td>
      </tr>`,
    )
    .join('')
  const trafficRows = report.developer.traffic
    .map(
      (item) => `<tr><td>${escapeHtml(item.method)}</td><td>${escapeHtml(item.endpoint)}</td><td>${item.status}</td><td>${escapeHtml(item.outcome)}</td><td>${item.request_count}</td><td>${item.approximate_request_bytes}</td><td>${item.approximate_response_bytes}</td></tr>`,
    )
    .join('')
  const nodeAccuracyRows = summary.per_node_accuracy
    .map(
      (item) => `<tr><td>${escapeHtml(item.node)}</td><td>${item.correct} / ${item.responses}</td><td>${percent(item.accuracy)}</td></tr>`,
    )
    .join('')
  const posteriorRows = summary.final_posterior
    .map(
      (probability, index) => `<tr><td>${index + 1}</td><td>${number(probability)}</td><td><div class="bar"><i style="width:${clampedPercent(probability)}%"></i></div></td></tr>`,
    )
    .join('')
  const timelineRows = report.developer.timeline
    .map(
      (stage) => `<tr><td>${escapeHtml(stage.stage)}</td><td>${escapeHtml(formatTimestamp(stage.started_at))}</td><td>${stage.ended_at ? escapeHtml(formatTimestamp(stage.ended_at)) : '—'}</td><td>${milliseconds(stage.duration_ms)}</td><td>${escapeHtml(stage.outcome)}</td></tr>`,
    )
    .join('')
  const dependencyRows = [
    ...report.developer.r_by_operation.map((item) => ({
      category: 'R',
      ...item,
    })),
    ...report.developer.supabase_by_operation.map((item) => ({
      category: 'Supabase',
      ...item,
    })),
  ]
    .map(
      (item) => `<tr><td>${item.category}</td><td>${escapeHtml(item.operation)}</td><td>${item.count}</td><td>${milliseconds(item.total_ms)}</td><td>${milliseconds(item.mean_ms)}</td><td>${milliseconds(item.maximum_ms)}</td></tr>`,
    )
    .join('')
  const slowRows = [
    ...report.developer.slowest_api_requests,
    ...report.developer.slowest_r_calls,
    ...report.developer.slowest_supabase_operations,
  ]
    .map(
      (item) => `<tr><td>${escapeHtml(item.category)}</td><td>${escapeHtml(item.operation)}</td><td>${milliseconds(item.duration_ms)}</td><td>${escapeHtml(item.request_id ?? '—')}</td><td>${item.sequence ?? '—'}</td><td>${item.diagnostic_flag ? 'märgitud' : 'alla läve'}</td></tr>`,
    )
    .join('')
  const warningList = report.data_quality_warnings
    .map((warning) => `<li>${escapeHtml(warning)}</li>`)
    .join('')
  const rAppendices = report.exact_r_calls
    .map(
      (call) => `<details><summary>#${call.sequence} ${escapeHtml(call.operation)} · ${milliseconds(call.duration_ms)} · ${escapeHtml(call.outcome)}</summary><h4>Puhastatud täpne sisend</h4><pre>${escapeHtml(JSON.stringify(call.input, null, 2))}</pre><h4>Puhastatud täpne väljund</h4><pre>${escapeHtml(JSON.stringify(call.output, null, 2))}</pre></details>`,
    )
    .join('')

  return `<!doctype html>
<html lang="et"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Simulatsiooniaruanne ${escapeHtml(report.test_id ?? report.experiment_id)}</title>
<style>
:root{font-family:Inter,ui-sans-serif,system-ui,sans-serif;color:#1f2c27;background:#f4f4ed}*{box-sizing:border-box}body{margin:0}main{max-width:1400px;margin:auto;padding:40px 24px 80px}h1,h2,h3{font-family:Georgia,serif}h1{margin:.2rem 0;font-size:2.3rem}h2{margin-top:2.5rem;border-bottom:1px solid #cfd5cb;padding-bottom:.5rem}.eyebrow{color:#65756d;text-transform:uppercase;letter-spacing:.12em;font-size:.72rem;font-weight:700}.badges{display:flex;gap:8px;flex-wrap:wrap;margin:18px 0}.badge{padding:6px 10px;border-radius:999px;background:#dfeade;color:#315b3d;font-size:.72rem;font-weight:700}.badge.partial,.warning{background:#f5e5cf;color:#7c522a}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:12px}.card{background:#fff;border:1px solid #d9ddd4;border-radius:10px;padding:16px}.card span,small{color:#69766f;font-size:.7rem}.card strong{display:block;margin-top:5px;font-size:1rem;overflow-wrap:anywhere}.note{padding:14px 16px;border-left:4px solid #718b76;background:#e9efe6;line-height:1.55}table{width:100%;border-collapse:collapse;background:#fff;font-size:.75rem}th,td{padding:9px;border:1px solid #d9ddd4;text-align:left;vertical-align:top}th{background:#e8ece5}.table-wrap{overflow:auto}.bar{width:100px;height:6px;margin-top:5px;border-radius:4px;background:#e0e5df}.bar i{display:block;height:100%;border-radius:4px;background:#66866f}code,pre{font-family:ui-monospace,SFMono-Regular,monospace}pre{max-height:600px;overflow:auto;padding:14px;background:#12221d;color:#d4dfd8;border-radius:8px;font-size:.68rem;white-space:pre-wrap;word-break:break-word}details{margin:9px 0;padding:12px;background:#fff;border:1px solid #d9ddd4;border-radius:8px}summary{cursor:pointer;font-weight:700}.profiles{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:10px}.profiles div{padding:12px;background:#fff;border:1px solid #d9ddd4;border-radius:8px}.profiles strong{display:block;margin-bottom:5px;font-size:.76rem}@media print{main{max-width:none;padding:0}.table-wrap{overflow:visible}details{break-inside:avoid}}
</style></head><body><main>
<p class="eyebrow">Testi simulatsioon · skeem ${escapeHtml(report.schema_version)}</p>
<h1>Uurimis- ja jõudlusaruanne</h1>
<p><code>${escapeHtml(report.test_id ?? 'Testi ID puudub')}</code></p>
<div class="badges"><span class="badge ${report.completion_state}">${escapeHtml(report.completion_state === 'completed' ? 'lõpetatud' : 'osaline')}</span><span class="badge">${escapeHtml(reportStatusLabels[report.run_status] ?? report.run_status)}</span><span class="badge">${report.event_count} säilitatud sündmust</span>${report.buffer_truncated ? '<span class="badge partial">puhver kärbitud</span>' : ''}</div>
<p class="note">${escapeHtml(report.research.interpretation)}</p>
<div class="grid">
  ${card('Loodud (UTC)', formatTimestamp(report.generated_at))}
  ${card('Katse', report.experiment_id)}
  ${card('Vastuseid', String(summary.response_count))}
  ${card('Täpsus', percent(summary.overall_accuracy))}
  ${card('Peatumise põhjus', summary.stopping_reason ?? 'Puudulik')}
  ${card('Lõplik usaldus', percent(profile?.best_state_confidence ?? null))}
</div>
<h2>Uurimisvaade</h2>
<div class="grid">
  ${card('Teadmiste sõlmed', values(metadata.nodes))}
  ${card('Seosed', metadata.relations.map((relation) => `${escapeHtml(relation.prerequisite)} → ${escapeHtml(relation.dependent)}`).join(' · ') || '—', true)}
  ${card('Seadistuse räsi', metadata.configuration_hash ?? '—')}
  ${card('Peatumise usaldus', percent(metadata.stop_confidence))}
  ${card('Teadmisseisundid', String(metadata.knowledge_state_count))}
  ${card('Algprior', metadata.initial_prior.length ? metadata.initial_prior.map((value) => value.toFixed(4)).join(' · ') : '—')}
  ${card('Usaldusväärsuse alampiir / turvapiir', `${metadata.reliability_floor.derived_floor ?? '—'} / ${metadata.safety_cap.derived_cap ?? '—'}`)}
</div>
<h3>Kohanduvad sammud</h3><div class="table-wrap"><table><thead><tr><th>Samm</th><th>Aeg</th><th>Kandidaat / sõlm</th><th>Parameetrid</th><th>Vastus</th><th>Interaktsioon</th><th>Süsteem</th><th>Maksimaalne usaldus</th><th>Entroopia</th><th>TV-liikumine</th><th>Otsus</th><th>R-i aeg</th></tr></thead><tbody>${rows || '<tr><td colspan="12">Kohanduvaid samme ei säilitatud.</td></tr>'}</tbody></table></div>
<div class="grid">
  <div><h3>Täpsus sõlmede kaupa</h3><div class="table-wrap"><table><thead><tr><th>Sõlm</th><th>Õiged</th><th>Täpsus</th></tr></thead><tbody>${nodeAccuracyRows || '<tr><td colspan="3">Hinnatud vastuseid ei säilitatud.</td></tr>'}</tbody></table></div></div>
  <div><h3>Lõplik posterior</h3><div class="table-wrap"><table><thead><tr><th>Seisundi indeks</th><th>Tõenäosus</th><th>Usaldus</th></tr></thead><tbody>${posteriorRows || '<tr><td colspan="3">Lõplikku posteriori ei säilitatud.</td></tr>'}</tbody></table></div></div>
</div>
<h3>Lõpliku profiili kategooriad</h3><div class="profiles">
  ${profileCard('Omandatud', profile?.mastered ?? [])}
  ${profileCard('Valmis õppima', profile?.ready_to_learn ?? [])}
  ${profileCard('Ebakindlus eesolevas', profile?.uncertain_ahead ?? [])}
  ${profileCard('Ebakindlus eeltingimuses', profile?.uncertain_prerequisite ?? [])}
  ${profileCard('Veel mitte', profile?.not_yet ?? [])}
</div>
<h2>Tehniline vaade</h2>
<div class="grid">
  ${card('API koguaeg', milliseconds(report.developer.api_latency.total_ms))}
  ${card('API mediaan / maksimum', `${milliseconds(report.developer.api_latency.median_ms)} / ${milliseconds(report.developer.api_latency.maximum_ms)}`)}
  ${card('R / Supabase', `${milliseconds(report.developer.backend_time.r_ms)} / ${milliseconds(report.developer.backend_time.supabase_ms)}`)}
  ${card('Rakenduse ülejäänud aeg', milliseconds(report.developer.backend_time.residual_application_ms))}
  ${card('Viimane edukas etapp', report.developer.last_successful_stage)}
  ${card('Viimane sündmus', report.developer.last_recorded_event)}
</div>
<p class="note">${escapeHtml(report.developer.thresholds.interpretation)} API ≥ ${report.developer.thresholds.api_request_ms} ms; sõltuvus ≥ ${report.developer.thresholds.dependency_call_ms} ms; ettevalmistus ≥ ${report.developer.thresholds.preparation_ms} ms.</p>
<h3>Katse ajajoon</h3><div class="table-wrap"><table><thead><tr><th>Etapp</th><th>Algus</th><th>Lõpp</th><th>Kestus</th><th>Tulemus</th></tr></thead><tbody>${timelineRows || '<tr><td colspan="5">Elutsükli etappe ei säilitatud.</td></tr>'}</tbody></table></div>
<h3>API liiklus</h3><div class="table-wrap"><table><thead><tr><th>Meetod</th><th>Otspunkt</th><th>Olek</th><th>Tulemus</th><th>Arv</th><th>Päringu baidid</th><th>Vastuse baidid</th></tr></thead><tbody>${trafficRows || '<tr><td colspan="7">Täielikke API-päringuid ei säilitatud.</td></tr>'}</tbody></table></div>
<h3>Sõltuvuste toimingud</h3><div class="table-wrap"><table><thead><tr><th>Sõltuvus</th><th>Toiming</th><th>Arv</th><th>Kokku</th><th>Keskmine</th><th>Maksimum</th></tr></thead><tbody>${dependencyRows || '<tr><td colspan="6">Ajastatud sõltuvustoiminguid ei säilitatud.</td></tr>'}</tbody></table></div>
<h3>Viis aeglaseimat kategooria kohta</h3><div class="table-wrap"><table><thead><tr><th>Kategooria</th><th>Toiming</th><th>Kestus</th><th>Päringu ID</th><th>Järjekord</th><th>Ülevaatamise märge</th></tr></thead><tbody>${slowRows || '<tr><td colspan="6">Ajastatud toiminguid ei säilitatud.</td></tr>'}</tbody></table></div>
<h3>Andmekvaliteet ja diagnostika</h3>${warningList ? `<ul class="warning">${warningList}</ul>` : '<p>Andmekvaliteedi hoiatusi pole.</p>'}
<h2>R-i puhastatud lisa</h2><p>Sisaldab ainult lubatud R-lepingu välju. Kliendi päringuid ning osaleja, küsimuse ja vastuse sisu ei kaasata.</p>${rAppendices || '<p>R-i päringuid ei säilitatud.</p>'}
</main></body></html>`
}

function download(content: string, filename: string, type: string) {
  const url = URL.createObjectURL(new Blob([content], { type }))
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = filename
  anchor.click()
  URL.revokeObjectURL(url)
}

function safeFilenamePart(value: string) {
  return value.replace(/[^a-zA-Z0-9_.-]/g, '_')
}

function escapeHtml(value: string) {
  return value
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#39;')
}

function formatTimestamp(value: string) {
  return new Date(value).toISOString()
}

function clampedPercent(value: number | null) {
  return value === null ? 0 : Math.max(0, Math.min(100, value * 100))
}

function number(value: number | null) {
  return value === null ? '—' : value.toFixed(4)
}

function card(label: string, value: string, valueIsHtml = false) {
  return `<div class="card"><span>${escapeHtml(label)}</span><strong>${valueIsHtml ? value : escapeHtml(value)}</strong></div>`
}

function profileCard(label: string, values: string[]) {
  return `<div><strong>${escapeHtml(label)}</strong>${values.length ? values.map(escapeHtml).join(' · ') : '—'}</div>`
}
