import { act, cleanup, fireEvent, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import App from './App'
import { playerCredentialStorageKey } from './credential'
import {
  PlayerApiError,
  type ActiveResult,
  type CompletedResult,
  type PlayerApi,
} from './api'

const testId = 'abcd1234-5678-4abc-8def-1234567890ab'
const path = `/test/${testId}`

function active(
  submissionId = '11111111-1111-4111-8111-111111111111',
  prompt = 'Mis on kaks pluss kaks?',
): ActiveResult {
  return {
    status: 'active',
    question: {
      submission_id: submissionId,
      item_id: 987,
      instruction: 'Vali üks vastus.',
      prompt,
      stimulus: 'Arvuta enne vastamist.',
      options: [
        { id: 'option-three', text: 'Kolm' },
        { id: 'option-four', text: 'Neli' },
        { id: 'option-five', text: 'Viis' },
      ],
    },
  }
}

const completed: CompletedResult = {
  status: 'completed',
  feedback: {
    already_mastered: ['Liitmine'],
    learn_next: ['Lahutamine'],
    review: ['Murrud'],
    summary: 'Test on lõpetatud.',
    confidence_limited: false,
  },
}

function mockApi(
  start: PlayerApi['start'] = vi.fn().mockResolvedValue(active()),
  submit: PlayerApi['submit'] = vi.fn().mockResolvedValue(completed),
): PlayerApi {
  return { start, submit }
}

function beginTest() {
  fireEvent.click(screen.getByRole('button', { name: 'Alusta testi' }))
}

afterEach(() => {
  cleanup()
  sessionStorage.clear()
  vi.useRealTimers()
  vi.restoreAllMocks()
})

describe('welcome screen', () => {
  it('waits for the student before starting the test', async () => {
    const start = vi.fn<PlayerApi['start']>().mockResolvedValue(active())
    render(<App api={mockApi(start)} pathname={path} />)

    expect(screen.getByRole('heading', { name: 'Õpiraja test' })).toBeInTheDocument()
    expect(start).not.toHaveBeenCalled()

    beginTest()

    expect(
      await screen.findByRole('group', { name: 'Mis on kaks pluss kaks?' }),
    ).toBeInTheDocument()
    expect(start).toHaveBeenCalledTimes(1)
  })

  it('opens and closes the test information dialog', async () => {
    const user = userEvent.setup()
    render(<App api={mockApi()} pathname={path} />)

    await user.click(screen.getByRole('button', { name: 'Testi info' }))
    expect(screen.getByRole('dialog', { name: 'Kuidas test töötab?' })).toBeInTheDocument()
    expect(screen.getByText(/kohandub sinu vastuste järgi/)).toBeInTheDocument()

    await user.keyboard('{Escape}')
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Testi info' })).toHaveFocus()
  })
})

describe('test link bootstrap', () => {
  it.each(['/test', '/test/', '/test/nope', `${path}/extra`])(
    'renders an invalid link without requesting %s',
    (pathname) => {
      const start = vi.fn<PlayerApi['start']>().mockResolvedValue(active())
      const api = mockApi(start)
      render(<App api={api} pathname={pathname} />)

      expect(
        screen.getByRole('heading', { name: 'Testi link ei ole kehtiv' }),
      ).toBeInTheDocument()
      expect(start).not.toHaveBeenCalled()
    },
  )

  it('moves an exact fragment token to test-specific session storage before API work', async () => {
    window.history.replaceState({}, '', `${path}#token=signed-player-jwt`)
    const start = vi.fn<PlayerApi['start']>().mockResolvedValue(active())
    const api = mockApi(start)
    render(<App api={api} />)
    beginTest()

    await screen.findByRole('group', { name: 'Mis on kaks pluss kaks?' })
    expect(start).toHaveBeenCalledWith(testId, expect.any(AbortSignal))
    expect(window.location.hash).toBe('')
    expect(sessionStorage.getItem(playerCredentialStorageKey(testId))).toBe(
      'signed-player-jwt',
    )
  })

  it('does not accept query credentials or another test token', async () => {
    const otherId = 'bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb'
    sessionStorage.setItem(playerCredentialStorageKey(otherId), 'other-token')
    window.history.replaceState({}, '', `${path}?token=query-token`)
    const start = vi.fn<PlayerApi['start']>().mockResolvedValue(active())
    render(<App api={mockApi(start)} />)
    beginTest()

    await screen.findByRole('group', { name: 'Mis on kaks pluss kaks?' })
    expect(sessionStorage.getItem(playerCredentialStorageKey(testId))).toBeNull()
    expect(sessionStorage.getItem(playerCredentialStorageKey(otherId))).toBe(
      'other-token',
    )
  })
})

describe('preparation polling', () => {
  it('starts immediately and waits Retry-After plus fresh positive jitter', async () => {
    vi.useFakeTimers()
    const start = vi
      .fn<PlayerApi['start']>()
      .mockResolvedValueOnce({ status: 'preparing', retryAfterSeconds: 3 })
      .mockResolvedValueOnce(active())
    render(<App api={mockApi(start)} pathname={path} random={() => 0.25} />)
    beginTest()

    await act(async () => {})
    expect(start).toHaveBeenCalledTimes(1)
    expect(screen.getByRole('status')).toHaveTextContent('Testi kavandatakse')

    await act(() => vi.advanceTimersByTimeAsync(3250))
    expect(start).toHaveBeenCalledTimes(1)
    await act(() => vi.advanceTimersByTimeAsync(1))
    expect(start).toHaveBeenCalledTimes(2)
    expect(
      screen.getByRole('group', { name: 'Mis on kaks pluss kaks?' }),
    ).toBeInTheDocument()
  })

  it('uses fresh jitter for every 202 and keeps one request per cycle', async () => {
    vi.useFakeTimers()
    const random = vi.fn().mockReturnValueOnce(0).mockReturnValueOnce(0.999)
    const start = vi
      .fn<PlayerApi['start']>()
      .mockResolvedValueOnce({ status: 'preparing', retryAfterSeconds: 1 })
      .mockResolvedValueOnce({ status: 'preparing', retryAfterSeconds: 1 })
      .mockResolvedValueOnce(completed)
    render(<App api={mockApi(start)} pathname={path} random={random} />)
    beginTest()

    await act(async () => {})
    await act(() => vi.advanceTimersByTimeAsync(1001))
    expect(start).toHaveBeenCalledTimes(2)
    await act(() => vi.advanceTimersByTimeAsync(2000))
    expect(start).toHaveBeenCalledTimes(3)
    expect(random).toHaveBeenCalledTimes(2)
    expect(
      screen.getByRole('heading', { name: 'Sinu tagasiside' }),
    ).toBeInTheDocument()
  })

  it('does not poll after success or failure', async () => {
    vi.useFakeTimers()
    const success = vi.fn<PlayerApi['start']>().mockResolvedValue(active())
    const first = render(<App api={mockApi(success)} pathname={path} />)
    beginTest()
    await act(async () => {})
    await act(() => vi.advanceTimersByTimeAsync(20_000))
    expect(success).toHaveBeenCalledTimes(1)
    first.unmount()

    const failure = vi
      .fn<PlayerApi['start']>()
      .mockRejectedValue(new PlayerApiError('not_found'))
    render(<App api={mockApi(failure)} pathname={path} />)
    beginTest()
    await act(async () => {})
    await act(() => vi.advanceTimersByTimeAsync(20_000))
    expect(failure).toHaveBeenCalledTimes(1)
  })

  it('clears its timer and aborts the request on unmount', async () => {
    vi.useFakeTimers()
    let signal: AbortSignal | undefined
    const start = vi.fn<PlayerApi['start']>((_testId, requestSignal) => {
      signal = requestSignal
      return Promise.resolve({ status: 'preparing', retryAfterSeconds: 3 })
    })
    const view = render(<App api={mockApi(start)} pathname={path} />)
    beginTest()
    await act(async () => {})

    view.unmount()
    expect(signal?.aborted).toBe(true)
    await act(() => vi.advanceTimersByTimeAsync(10_000))
    expect(start).toHaveBeenCalledTimes(1)
  })
})

describe('question interaction and submission', () => {
  it('preserves option order and supports native keyboard radio interaction', async () => {
    const user = userEvent.setup()
    render(<App api={mockApi()} pathname={path} />)
    beginTest()

    const radios = await screen.findAllByRole('radio')
    expect(radios.map((radio) => radio.getAttribute('value'))).toEqual([
      'option-three',
      'option-four',
      'option-five',
    ])
    expect(screen.getByText('Vali üks vastus.')).toBeInTheDocument()
    expect(screen.getByText('Arvuta enne vastamist.')).toBeInTheDocument()
    const submit = screen.getByRole('button', { name: 'Edasi' })
    expect(submit).toBeDisabled()

    radios[0].focus()
    await user.keyboard(' ')
    expect(radios[0]).toBeChecked()
    expect(submit).toBeEnabled()
  })

  it('captures opaque IDs, disables controls, and prevents double submission', async () => {
    const pending = new Promise<CompletedResult>(() => undefined)
    const submit = vi.fn<PlayerApi['submit']>().mockReturnValue(pending)
    const user = userEvent.setup()
    render(<App api={mockApi(undefined, submit)} pathname={path} />)
    beginTest()

    await user.click(await screen.findByLabelText('Neli'))
    await user.dblClick(screen.getByRole('button', { name: 'Edasi' }))

    expect(submit).toHaveBeenCalledTimes(1)
    expect(submit).toHaveBeenCalledWith(
      testId,
      {
        submission_id: '11111111-1111-4111-8111-111111111111',
        option_id: 'option-four',
      },
      expect.any(AbortSignal),
    )
    expect(screen.getByRole('button', { name: 'Saadan…' })).toBeDisabled()
    expect(screen.getByRole('status')).toHaveTextContent('salvestatakse')
  })

  it('resets selection for the next persisted question and reveals no correctness', async () => {
    const next = active(
      '22222222-2222-4222-8222-222222222222',
      'Milline arv on suurem?',
    )
    const user = userEvent.setup()
    render(
      <App
        api={mockApi(undefined, vi.fn().mockResolvedValue(next))}
        pathname={path}
      />,
    )
    beginTest()

    await user.click(await screen.findByLabelText('Neli'))
    await user.click(screen.getByRole('button', { name: 'Edasi' }))

    expect(
      await screen.findByRole('group', { name: 'Milline arv on suurem?' }),
    ).toBeInTheDocument()
    expect(screen.getByLabelText('Neli')).not.toBeChecked()
    expect(screen.queryByText(/õige|vale/i)).not.toBeInTheDocument()
    expect(screen.queryByText(/987/)).not.toBeInTheDocument()
  })

  it('retries an uncertain answer with byte-equivalent captured identifiers', async () => {
    const submit = vi
      .fn<PlayerApi['submit']>()
      .mockRejectedValueOnce(new PlayerApiError('network', { requestId: 'req-7' }))
      .mockResolvedValueOnce(completed)
    const user = userEvent.setup()
    render(<App api={mockApi(undefined, submit)} pathname={path} />)
    beginTest()

    await user.click(await screen.findByLabelText('Neli'))
    await user.click(screen.getByRole('button', { name: 'Edasi' }))
    expect(await screen.findByText('Viitenumber: req-7')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Proovi uuesti' }))
    await screen.findByRole('heading', { name: 'Sinu tagasiside' })

    expect(submit).toHaveBeenCalledTimes(2)
    expect(JSON.stringify(submit.mock.calls[1][1])).toBe(
      JSON.stringify(submit.mock.calls[0][1]),
    )
  })

  it('recovers from 409 by calling start for authoritative state', async () => {
    const advanced = active(
      '33333333-3333-4333-8333-333333333333',
      'Backendist taastatud küsimus',
    )
    const start = vi
      .fn<PlayerApi['start']>()
      .mockResolvedValueOnce(active())
      .mockResolvedValueOnce(advanced)
    const submit = vi
      .fn<PlayerApi['submit']>()
      .mockRejectedValue(new PlayerApiError('conflict'))
    const user = userEvent.setup()
    render(<App api={mockApi(start, submit)} pathname={path} />)
    beginTest()

    await user.click(await screen.findByLabelText('Kolm'))
    await user.click(screen.getByRole('button', { name: 'Edasi' }))
    await user.click(
      await screen.findByRole('button', { name: 'Laadi test uuesti' }),
    )

    expect(
      await screen.findByRole('group', { name: 'Backendist taastatud küsimus' }),
    ).toBeInTheDocument()
    expect(start).toHaveBeenCalledTimes(2)
    expect(submit).toHaveBeenCalledTimes(1)
  })

  it.each([
    ['forbidden', 'Vastust ei saa saata.'],
    ['not_found', 'Testi ei leitud.'],
    ['validation', 'Vastust ei saa saata.'],
  ] as const)('shows terminal generic copy for %s', async (kind, message) => {
    const submit = vi
      .fn<PlayerApi['submit']>()
      .mockRejectedValue(new PlayerApiError(kind, { requestId: 'terminal-id' }))
    const user = userEvent.setup()
    render(<App api={mockApi(undefined, submit)} pathname={path} />)
    beginTest()

    await user.click(await screen.findByLabelText('Kolm'))
    await user.click(screen.getByRole('button', { name: 'Edasi' }))

    expect(await screen.findByRole('heading', { name: message })).toBeInTheDocument()
    expect(screen.queryByRole('button')).not.toBeInTheDocument()
    expect(screen.getByText('Viitenumber: terminal-id')).toBeInTheDocument()
  })
})

describe('completion and reload recovery', () => {
  it('always renders all feedback sections, summary, and legacy empty copy', async () => {
    const feedback: CompletedResult = {
      status: 'completed',
      feedback: {
        already_mastered: [],
        learn_next: [],
        review: [],
        summary: null,
        confidence_limited: true,
      },
    }
    render(<App api={mockApi(vi.fn().mockResolvedValue(feedback))} pathname={path} />)
    beginTest()

    expect(await screen.findByText('Juba oskad')).toBeInTheDocument()
    expect(screen.getByText('Võid õppida / rohkem süveneda')).toBeInTheDocument()
    expect(screen.getByText('Tasuks korrata')).toBeInTheDocument()
    expect(
      screen.getByText('Sellest testist ei leidnud me veel midagi kindlalt kinnitatut.'),
    ).toBeInTheDocument()
    expect(screen.getByText('Hetkel pole uut suunda pakkuda.')).toBeInTheDocument()
    expect(screen.getByText('Midagi kindlat kordamist ei vaja.')).toBeInTheDocument()
    expect(screen.getByText(/piisavalt kindlalt eristada/)).toBeInTheDocument()
  })

  it('remounts from backend state instead of browser storage', async () => {
    localStorage.setItem('question', 'forbidden-browser-state')
    sessionStorage.setItem('answer', 'forbidden-browser-state')
    const start = vi
      .fn<PlayerApi['start']>()
      .mockResolvedValueOnce(active())
      .mockResolvedValueOnce(
        active('44444444-4444-4444-8444-444444444444', 'Taastatud pärast laadimist'),
      )
      .mockResolvedValueOnce(completed)
    const api = mockApi(start)

    const first = render(<App api={api} pathname={path} />)
    beginTest()
    await screen.findByRole('group', { name: 'Mis on kaks pluss kaks?' })
    first.unmount()
    const second = render(<App api={api} pathname={path} />)
    beginTest()
    await screen.findByRole('group', { name: 'Taastatud pärast laadimist' })
    second.unmount()
    render(<App api={api} pathname={path} />)
    beginTest()
    await screen.findByRole('heading', { name: 'Sinu tagasiside' })

    expect(start).toHaveBeenCalledTimes(3)
    expect(document.body).not.toHaveTextContent('forbidden-browser-state')
  })
})
