import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import App from './App'
import { ItemsPage } from './ItemsPage'
import { MaterialsPage } from './MaterialsPage'

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
      await screen.findByText('Valid admin credentials are required.'),
    ).toBeInTheDocument()
    expect(sessionStorage.getItem('assessment-admin-access-key')).toBeNull()
  })
})

it('validates rule JSON before sending a write', async () => {
  const fetchMock = vi.fn(() => response([]))
  vi.stubGlobal('fetch', fetchMock)
  const user = userEvent.setup()

  render(
    <MaterialsPage
      accessKey="key"
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
  render(<ItemsPage accessKey="key" courses={[]} />)

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
