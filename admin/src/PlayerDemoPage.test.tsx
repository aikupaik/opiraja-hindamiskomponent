import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { PlayerDemoPage } from './PlayerDemoPage'

const course = [{ value: 'FÜS101', title: 'Physics', label: 'Physics (FÜS101)' }]
const testId = '10000000-0000-4000-8000-000000000001'

function response(body: unknown, status = 200) {
  return Promise.resolve(
    new Response(JSON.stringify(body), {
      status,
      headers: { 'Content-Type': 'application/json' },
    }),
  )
}

function created(status: 'active' | 'preparing' = 'active') {
  return {
    test_id: testId,
    status,
    player_url: `/test/${testId}`,
    missing_nodes: [],
  }
}

function submitDefinition() {
  fireEvent.change(
    screen.getByPlaceholderText('Õpitulemus / teadmiste sõlm'),
    { target: { value: 'Motion' } },
  )
  fireEvent.click(screen.getByRole('button', { name: 'Loo testimängija test' }))
}

afterEach(() => {
  cleanup()
  vi.useRealTimers()
  vi.unstubAllGlobals()
})

describe('player demo', () => {
  it('creates through the OR boundary, exposes the link, and renders completed feedback', async () => {
    const writeText = vi.fn(() => Promise.resolve())
    vi.stubGlobal('navigator', { ...navigator, clipboard: { writeText } })
    const fetchMock = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const path = String(input)
      if (path === '/api/v1/tests' && init?.method === 'POST') {
        return response(created())
      }
      if (path === `/api/v1/tests/${testId}`) {
        return response({
          status: 'completed',
          feedback: {
            already_mastered: ['Motion'],
            learn_next: ['Force'],
            review: [],
            summary: 'Demo complete',
            confidence_limited: false,
          },
        })
      }
      return response({}, 404)
    })
    vi.stubGlobal('fetch', fetchMock)

    render(
      <PlayerDemoPage courses={course} maxGraphNodes={10} />,
    )
    submitDefinition()

    const openLink = await screen.findByRole('link', { name: 'Ava uuel vahelehel' })
    expect(openLink).toHaveAttribute('href', `http://localhost:3000/test/${testId}`)
    expect(openLink).toHaveAttribute('target', '_blank')
    expect(await screen.findByText('Demo complete')).toBeInTheDocument()
    expect(screen.getByText('Motion')).toBeInTheDocument()
    expect(screen.getByText('Force')).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: 'Kopeeri' }))
    await waitFor(() => expect(writeText).toHaveBeenCalledWith(
      `http://localhost:3000/test/${testId}`,
    ))
    expect(await screen.findByText('Testimängija URL on kopeeritud.')).toBeInTheDocument()

    const createCall = fetchMock.mock.calls.find(([input]) => String(input) === '/api/v1/tests')
    expect(JSON.parse(String(createCall?.[1]?.body))).toEqual({
      user_id: 'admin-simulation-user',
      learning_path_id: 'manual-experiment',
      course: 'FÜS101',
      goal: 'trial_run',
      method: 'kst',
      cognitive_level: 'mõistab',
      nodes: ['Motion'],
      relations: [],
    })
    expect(
      fetchMock.mock.calls.every(([input]) =>
        !String(input).includes('/player/') && !String(input).includes('/events'),
      ),
    ).toBe(true)
  })

  it('polls sequentially and aborts an outstanding status request on unmount', async () => {
    vi.useFakeTimers()
    let statusCalls = 0
    let statusSignal: AbortSignal | undefined
    const fetchMock = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const path = String(input)
      if (path === '/api/v1/tests') return response(created('preparing'))
      if (path === `/api/v1/tests/${testId}`) {
        statusCalls += 1
        if (statusCalls === 1) return response({ status: 'active' })
        statusSignal = init?.signal ?? undefined
        return new Promise<Response>(() => undefined)
      }
      return response({}, 404)
    })
    vi.stubGlobal('fetch', fetchMock)

    const rendered = render(
      <PlayerDemoPage courses={course} maxGraphNodes={10} />,
    )
    submitDefinition()
    await act(async () => Promise.resolve())
    await act(async () => Promise.resolve())

    expect(statusCalls).toBe(1)
    await act(async () => {
      vi.advanceTimersByTime(2999)
    })
    expect(statusCalls).toBe(1)
    await act(async () => {
      vi.advanceTimersByTime(1)
    })
    expect(statusCalls).toBe(2)

    rendered.unmount()
    expect(statusSignal?.aborted).toBe(true)
  })
})
