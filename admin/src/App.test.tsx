import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import App from './App'
import { isVisibleDiagnostic } from './api'
import { ItemsPage } from './ItemsPage'
import { MaterialsPage } from './MaterialsPage'
import { SimulationPage } from './SimulationPage'
import { exampleReport } from './test/reportFixture'
import { createUuid } from './uuid'

const session = {
  subject: 'development-admin',
  capabilities: ['admin:read'],
  max_graph_nodes: 10,
  diagnostic_max_events: 500,
  diagnostic_ttl_seconds: 3600,
  source_max_bytes: 10_000_000,
  source_max_pdf_pages: 100,
  source_max_text_chars: 1_000_000,
}

function response(body: unknown, status = 200) {
  return Promise.resolve(
    new Response(JSON.stringify(body), {
      status,
      headers: { 'Content-Type': 'application/json' },
    }),
  )
}

beforeEach(() => {
  sessionStorage.clear()
  window.location.hash = '#/materials'
})

afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
})

describe('admin shell', () => {
  it('exchanges the key, stores only the JWT, and explicitly removes it', async () => {
    const fetchMock = vi
      .fn()
      .mockImplementationOnce(() =>
        response({
          access_token: 'signed-admin-jwt',
          token_type: 'Bearer',
          expires_in: 28_800,
          session,
        }),
      )
      .mockImplementationOnce(() => response([]))
    vi.stubGlobal('fetch', fetchMock)
    const user = userEvent.setup()

    render(<App />)
    await user.type(screen.getByLabelText('Administraatori ligipääsuvõti'), 'operator-key')
    await user.click(screen.getByRole('button', { name: 'Sisene' }))

    expect(
      await screen.findByRole('heading', { name: 'Kursuse materjalid' }),
    ).toBeInTheDocument()
    expect(sessionStorage.getItem('assessment-admin-jwt')).toBe(
      'signed-admin-jwt',
    )
    expect(JSON.stringify(sessionStorage)).not.toContain('operator-key')
    const [loginUrl, loginInit] = fetchMock.mock.calls[0]
    expect(loginUrl).toBe('/api/v1/admin/login')
    expect(loginInit.body).toBe(JSON.stringify({ access_key: 'operator-key' }))
    expect(loginInit.headers.get('Authorization')).toBeNull()
    await user.click(screen.getByRole('button', { name: 'Lukusta' }))
    expect(sessionStorage.getItem('assessment-admin-jwt')).toBeNull()
    expect(
      screen.getByRole('heading', { name: 'Ava hindamislabor' }),
    ).toBeInTheDocument()
  })

  it('keeps invalid credentials out of session storage', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(() =>
        response(
          {
            error: {
              code: 'admin_unauthorized',
              message: 'Valid admin credentials are required.',
            },
          },
          401,
        ),
      ),
    )
    const user = userEvent.setup()

    render(<App />)
    await user.type(screen.getByLabelText('Administraatori ligipääsuvõti'), 'wrong')
    await user.click(screen.getByRole('button', { name: 'Sisene' }))

    expect(
      await screen.findByText('Ligipääsuandmed ei sobi.'),
    ).toBeInTheDocument()
    expect(sessionStorage.getItem('assessment-admin-jwt')).toBeNull()
  })

  it('locks an authenticated session on 401 without treating login as expired', async () => {
    sessionStorage.setItem('assessment-admin-jwt', 'signed-admin-jwt')
    const fetchMock = vi
      .fn()
      .mockImplementationOnce(() => response(session))
      .mockImplementationOnce(() =>
        Promise.resolve(
          new Response(
            JSON.stringify({
              error: { code: 'admin_unauthorized', message: 'Hidden detail' },
            }),
            {
              status: 401,
              headers: {
                'Content-Type': 'application/json',
                'X-Request-ID': 'expired-request',
              },
            },
          ),
        ),
      )
    vi.stubGlobal('fetch', fetchMock)

    render(<App />)

    expect(
      await screen.findByText(
        'Seans aegus. Sisesta ligipääsuvõti uuesti.',
      ),
    ).toBeInTheDocument()
    expect(
      screen.getByRole('heading', { name: 'Ava hindamislabor' }),
    ).toBeInTheDocument()
    expect(sessionStorage.getItem('assessment-admin-jwt')).toBeNull()
  })

  it('routes authenticated operators to the Player demo tab', async () => {
    sessionStorage.setItem('assessment-admin-jwt', 'signed-admin-jwt')
    window.location.hash = '#/player-demo'
    vi.stubGlobal(
      'fetch',
      vi.fn()
        .mockImplementationOnce(() => response(session))
        .mockImplementationOnce(() => response([])),
    )

    render(<App />)

    expect(
      await screen.findByRole('heading', { name: 'Testimängija' }),
    ).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Testimängija' })).toHaveAttribute(
      'aria-current',
      'page',
    )
  })
})

it('validates rule JSON before sending a write', async () => {
  const fetchMock = vi.fn(() => response([]))
  vi.stubGlobal('fetch', fetchMock)
  const user = userEvent.setup()

  render(
    <MaterialsPage
      courses={[{ value: 'FÜS101', title: 'Physics', label: 'Physics (FÜS101)' }]}
      refreshCourses={() => Promise.resolve()}
    />,
  )
  await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2))
  await user.type(screen.getByLabelText('Reegli kirjeldus'), 'Use SI units')
  const editor = screen.getByLabelText('Korrektne JSON-näide')
  fireEvent.change(editor, { target: { value: '{broken' } })
  await user.click(screen.getByRole('button', { name: 'Salvesta reegel' }))

  expect(
    screen.getByText('Reegli näide peab olema korrektne ja mitte-null JSON.'),
  ).toBeInTheDocument()
  expect(fetchMock).toHaveBeenCalledTimes(2)
})

it('opens item editing in safe copy mode with complete measurements', async () => {
  vi.stubGlobal(
    'fetch',
    vi.fn(() =>
      response({
        items: [
          {
            yp_id: 41,
            course: 'FÜS101',
            graph_node: 'Force',
            parent_graph_node: null,
            cognitive_level: 'mõistab',
            instruction: 'Choose one.',
            prompt: 'What is force?',
            stimulus: null,
            answer_key: 'A',
            distractor_1: 'B',
            distractor_2: 'C',
            distractor_3: 'D',
            score: 1,
            irt_a: 1,
            irt_b: 0,
            beta_error: 0.05,
            guess_probability: 0.25,
            status: 'usable',
            usage_count: 7,
            last_used_at: null,
            created_at: null,
            updated_at: null,
          },
        ],
        total: 1,
        limit: 20,
        offset: 0,
      }),
    ),
  )
  const user = userEvent.setup()
  render(<ItemsPage courses={[]} />)

  await user.type(screen.getByLabelText('Täpne kursuse kood'), 'FÜS101')
  await user.click(screen.getByRole('button', { name: 'Otsi küsimusi' }))
  await user.click(await screen.findByRole('button', { name: 'Vaata' }))
  await user.click(screen.getByRole('button', { name: 'Ava muutmine' }))

  expect(screen.getByLabelText(/Loo muudetud koopia/)).toBeChecked()
  expect(screen.getByLabelText('BLIM-i β-viga')).toHaveValue(0.05)
  expect(
    screen.getByText(/Kasutusandmed lähtestatakse/),
  ).toBeInTheDocument()
})

it('adds an unselected relation with explicit prerequisite roles', async () => {
  HTMLElement.prototype.scrollTo = vi.fn()
  const user = userEvent.setup()
  render(
    <SimulationPage
      courses={[{ value: 'FÜS101', title: 'Physics', label: 'Physics (FÜS101)' }]}
      maxGraphNodes={10}
    />,
  )

  const firstNode = screen.getByPlaceholderText('Õpitulemus / teadmiste sõlm')
  await user.type(firstNode, 'Motion')
  await user.click(screen.getByRole('button', { name: '+ Lisa sõlm' }))
  const nodeInputs = screen.getAllByPlaceholderText(
    'Õpitulemus / teadmiste sõlm',
  )
  await user.type(nodeInputs[1], 'Force')
  await user.click(screen.getByRole('button', { name: '+ Lisa seos' }))

  expect(screen.getByLabelText('Eeltingimuse sõlm (vanem)')).toHaveValue('')
  expect(screen.getByLabelText('Sõltuv sõlm (laps)')).toHaveValue('')
  expect(
    screen.getByText(
      'Eeltingimuse sõlm (vanem)',
    ),
  ).toBeInTheDocument()
})

it('keeps Supabase diagnostics out of the visible terminal event set', () => {
  const baseEvent = {
    sequence: 1,
    timestamp: '2026-01-01T00:00:00Z',
    level: 'info',
    request_id: null,
    test_id: null,
    payload: {},
  }

  expect(
    isVisibleDiagnostic({
      ...baseEvent,
      source: 'supabase',
      type: 'supabase_operation',
    }),
  ).toBe(false)
  expect(
    isVisibleDiagnostic({
      ...baseEvent,
      source: 'fastapi',
      type: 'request_completed',
    }),
  ).toBe(true)
})

it('creates a UUID v4 when randomUUID is unavailable on HTTP origins', () => {
  vi.stubGlobal('crypto', {
    getRandomValues: (bytes: Uint8Array) => {
      bytes.set([
        0x00, 0x01, 0x02, 0x03, 0x04, 0x05, 0x06, 0x07,
        0x08, 0x09, 0x0a, 0x0b, 0x0c, 0x0d, 0x0e, 0x0f,
      ])
      return bytes
    },
  })

  expect(createUuid()).toBe(
    '00010203-0405-4607-8809-0a0b0c0d0e0f',
  )
})

it('preserves a cancelled experiment and automatically loads its partial report', async () => {
  const experimentId = '30000000-0000-4000-8000-000000000003'
  vi.stubGlobal('crypto', { randomUUID: () => experimentId })
  let reportAttempts = 0
  const fetchMock = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
    const path = String(input)
    if (path.endsWith('/report')) {
      reportAttempts += 1
      return reportAttempts === 1
        ? response(
            {
              error: {
                code: 'admin_not_found',
                message: 'Admin row was not found.',
              },
            },
            404,
          )
        : response(exampleReport)
    }
    if (path.includes('/events') || path === '/api/v1/tests') {
      return new Promise<Response>((_resolve, reject) => {
        init?.signal?.addEventListener(
          'abort',
          () => reject(new DOMException('Aborted', 'AbortError')),
          { once: true },
        )
      })
    }
    return response({}, 404)
  })
  vi.stubGlobal('fetch', fetchMock)
  const user = userEvent.setup()

  render(
    <SimulationPage
      courses={[{ value: 'FÜS101', title: 'Physics', label: 'Physics (FÜS101)' }]}
      maxGraphNodes={10}
    />,
  )
  await user.type(
    screen.getByPlaceholderText('Õpitulemus / teadmiste sõlm'),
    'Motion',
  )
  await user.click(screen.getByRole('button', { name: 'Käivita katse' }))
  await user.click(screen.getByRole('button', { name: 'Tühista' }))

  expect(
    await screen.findByRole('heading', { name: 'Simulatsiooniaruanne' }),
  ).toBeInTheDocument()
  expect(
    await screen.findByRole('button', { name: 'Proovi uuesti' }),
  ).toBeInTheDocument()
  await user.click(screen.getByRole('button', { name: 'Proovi uuesti' }))
  expect(await screen.findByText('Osaline')).toBeInTheDocument()
  expect(screen.getByText(experimentId)).toBeInTheDocument()
  expect(
    screen.getByRole('button', { name: 'Laadi HTML-aruanne alla' }),
  ).toBeInTheDocument()
  expect(
    fetchMock.mock.calls.some(([input]) => String(input).endsWith('/report')),
  ).toBe(true)
})

it('automatically loads a completed report after the final answer', async () => {
  vi.stubGlobal('crypto', {
    randomUUID: () => '30000000-0000-4000-8000-000000000003',
  })
  const fetchMock = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
    const path = String(input)
    if (path.includes('/events')) {
      return new Promise<Response>((_resolve, reject) => {
        init?.signal?.addEventListener(
          'abort',
          () => reject(new DOMException('Aborted', 'AbortError')),
          { once: true },
        )
      })
    }
    if (path === '/api/v1/tests') {
      return response({
        test_id: '10000000-0000-4000-8000-000000000001',
        status: 'active',
        player_url: '/test/10000000-0000-4000-8000-000000000001',
        missing_nodes: [],
      })
    }
    if (path.endsWith('/start')) {
      return response({
        status: 'active',
        question: {
          submission_id: '20000000-0000-4000-8000-000000000001',
          item_id: 41,
          instruction: 'Choose one.',
          prompt: 'Safe player-only question',
          stimulus: null,
          options: [{ id: 'option-1', text: 'Correct' }],
        },
      })
    }
    if (path.endsWith('/answers')) {
      return response({
        status: 'completed',
        feedback: {
          already_mastered: ['A'],
          learn_next: [],
          review: [],
          summary: 'Done',
          confidence_limited: false,
        },
      })
    }
    if (path.endsWith('/report')) {
      return response({
        ...exampleReport,
        completion_state: 'completed',
        run_status: 'completed',
        data_quality_warnings: [],
      })
    }
    return response({}, 404)
  })
  vi.stubGlobal('fetch', fetchMock)
  const user = userEvent.setup()

  render(
    <SimulationPage
      courses={[{ value: 'FÜS101', title: 'Physics', label: 'Physics (FÜS101)' }]}
      maxGraphNodes={10}
    />,
  )
  await user.type(
    screen.getByPlaceholderText('Õpitulemus / teadmiste sõlm'),
    'Motion',
  )
  await user.click(screen.getByRole('button', { name: 'Käivita katse' }))
  await user.click(
    await screen.findByRole('button', { name: /Correct/ }),
  )

  expect((await screen.findAllByText('Lõpetatud')).length).toBeGreaterThan(0)
  expect(
    screen.getByRole('button', { name: 'Laadi JSON-andmed alla' }),
  ).toBeInTheDocument()
})
