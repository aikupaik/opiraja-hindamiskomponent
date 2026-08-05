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
  it('validates, stores, and explicitly removes the tab-scoped key', async () => {
    const fetchMock = vi
      .fn()
      .mockImplementationOnce(() => response(session))
      .mockImplementationOnce(() => response([]))
    vi.stubGlobal('fetch', fetchMock)
    const user = userEvent.setup()

    render(<App />)
    await user.type(screen.getByLabelText('Admin access key'), 'operator-key')
    await user.click(screen.getByRole('button', { name: 'Enter console' }))

    expect(
      await screen.findByRole('heading', { name: 'Course materials' }),
    ).toBeInTheDocument()
    expect(sessionStorage.getItem('assessment-admin-access-key')).toBe(
      'operator-key',
    )
    await user.click(screen.getByRole('button', { name: 'Lock' }))
    expect(sessionStorage.getItem('assessment-admin-access-key')).toBeNull()
    expect(
      screen.getByRole('heading', { name: 'Unlock Assessment Lab' }),
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
    await user.type(screen.getByLabelText('Admin access key'), 'wrong')
    await user.click(screen.getByRole('button', { name: 'Enter console' }))

    expect(
      await screen.findByText('The credentials were not accepted.'),
    ).toBeInTheDocument()
    expect(sessionStorage.getItem('assessment-admin-access-key')).toBeNull()
  })

  it('locks an authenticated session on 401 without treating login as expired', async () => {
    sessionStorage.setItem('assessment-admin-access-key', 'operator-key')
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
        'Your session expired. Enter your credentials again.',
      ),
    ).toBeInTheDocument()
    expect(
      screen.getByRole('heading', { name: 'Unlock Assessment Lab' }),
    ).toBeInTheDocument()
    expect(sessionStorage.getItem('assessment-admin-access-key')).toBeNull()
  })

  it('routes authenticated operators to the Player demo tab', async () => {
    sessionStorage.setItem('assessment-admin-access-key', 'operator-key')
    window.location.hash = '#/player-demo'
    vi.stubGlobal(
      'fetch',
      vi.fn()
        .mockImplementationOnce(() => response(session))
        .mockImplementationOnce(() => response([])),
    )

    render(<App />)

    expect(
      await screen.findByRole('heading', { name: 'Test player demo' }),
    ).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Player demo' })).toHaveAttribute(
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
  await user.type(screen.getByLabelText('Rule description'), 'Use SI units')
  const editor = screen.getByLabelText('Valid JSON example')
  fireEvent.change(editor, { target: { value: '{broken' } })
  await user.click(screen.getByRole('button', { name: 'Save rule' }))

  expect(
    screen.getByText('Rule example must be valid, non-null JSON.'),
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

  await user.type(screen.getByLabelText('Exact course code'), 'FÜS101')
  await user.click(screen.getByRole('button', { name: 'Search item bank' }))
  await user.click(await screen.findByRole('button', { name: 'Inspect' }))
  await user.click(screen.getByRole('button', { name: 'Open editor' }))

  expect(screen.getByLabelText(/Create revised copy/)).toBeChecked()
  expect(screen.getByLabelText('BLIM β error')).toHaveValue(0.05)
  expect(
    screen.getByText(/Usage telemetry resets to zero/),
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

  const firstNode = screen.getByPlaceholderText('Learning outcome / graph node')
  await user.type(firstNode, 'Motion')
  await user.click(screen.getByRole('button', { name: '+ Add node' }))
  const nodeInputs = screen.getAllByPlaceholderText(
    'Learning outcome / graph node',
  )
  await user.type(nodeInputs[1], 'Force')
  await user.click(screen.getByRole('button', { name: '+ Add relation' }))

  expect(screen.getByLabelText('Prerequisite node (parent)')).toHaveValue('')
  expect(screen.getByLabelText('Dependent node (child)')).toHaveValue('')
  expect(
    screen.getByText(
      'The parent prerequisite must be learned before the child.',
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
    screen.getByPlaceholderText('Learning outcome / graph node'),
    'Motion',
  )
  await user.click(screen.getByRole('button', { name: 'Run experiment' }))
  await user.click(screen.getByRole('button', { name: 'Cancel' }))

  expect(
    await screen.findByRole('heading', { name: 'Simulation report' }),
  ).toBeInTheDocument()
  expect(
    await screen.findByRole('button', { name: 'Retry report' }),
  ).toBeInTheDocument()
  await user.click(screen.getByRole('button', { name: 'Retry report' }))
  expect(await screen.findByText('partial')).toBeInTheDocument()
  expect(screen.getByText(experimentId)).toBeInTheDocument()
  expect(
    screen.getByRole('button', { name: 'Download HTML report' }),
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
    screen.getByPlaceholderText('Learning outcome / graph node'),
    'Motion',
  )
  await user.click(screen.getByRole('button', { name: 'Run experiment' }))
  await user.click(
    await screen.findByRole('button', { name: /Correct/ }),
  )

  expect((await screen.findAllByText('completed')).length).toBeGreaterThan(0)
  expect(
    screen.getByRole('button', { name: 'Download JSON data' }),
  ).toBeInTheDocument()
})
