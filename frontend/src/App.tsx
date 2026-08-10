import { useEffect, useId, useRef, useState } from 'react'
import {
  PlayerApiError,
  playerApi,
  type PlayerApi,
  type PlayerFeedback,
  type PlayerQuestion,
  type PlayerQuestionResult,
  type SubmissionPayload,
} from './api'
import {
  bootstrapPlayerCredential,
  subscribeToPlayerCredentialExpiry,
} from './credential'
import { parseTestPath } from './path'
import './App.css'

type Recovery =
  | { kind: 'retry_start' | 'reload_start' }
  | {
      kind: 'retry_submission'
      question: PlayerQuestion
      selection: string
      payload: SubmissionPayload
    }

type PlayerState =
  | { kind: 'welcome' }
  | { kind: 'preparing'; requestKey: number }
  | { kind: 'question'; question: PlayerQuestion; selection: string | null }
  | {
      kind: 'submitting'
      question: PlayerQuestion
      selection: string
      payload: SubmissionPayload
      requestKey: number
    }
  | {
      kind: 'completed'
      feedback: PlayerFeedback
      questionResults: PlayerQuestionResult[]
    }
  | {
      kind: 'failed'
      message: string
      requestId: string | null
      recovery?: Recovery
    }

interface AppProps {
  api?: PlayerApi
  pathname?: string
  random?: () => number
}

function App({
  api = playerApi,
  pathname = window.location.pathname,
  random = Math.random,
}: AppProps) {
  const testId = parseTestPath(pathname)

  if (testId === null) {
    return <InvalidLink />
  }
  bootstrapPlayerCredential(testId)
  return <TestPlayer api={api} random={random} testId={testId} />
}

function TestPlayer({
  api,
  random,
  testId,
}: {
  api: PlayerApi
  random: () => number
  testId: string
}) {
  const [state, setState] = useState<PlayerState>({
    kind: 'welcome',
  })

  useEffect(
    () =>
      subscribeToPlayerCredentialExpiry(() => {
        setState({
          kind: 'failed',
          message: 'Testi link on aegunud.',
          requestId: null,
        })
      }),
    [],
  )

  useEffect(() => {
    if (state.kind !== 'preparing') return

    const controller = new AbortController()
    let current = true
    let timer: ReturnType<typeof setTimeout> | undefined

    const start = async () => {
      try {
        const result = await api.start(testId, controller.signal)
        if (!current) return
        if (result.status === 'active') {
          setState({ kind: 'question', question: result.question, selection: null })
          return
        }
        if (result.status === 'completed') {
          setState({
            kind: 'completed',
            feedback: result.feedback,
            questionResults: result.question_results,
          })
          return
        }
        const jitter = Math.floor(random() * 1000) + 1
        timer = setTimeout(() => {
          timer = undefined
          void start()
        }, result.retryAfterSeconds * 1000 + jitter)
      } catch (error) {
        if (!current || isAborted(error)) return
        setState(startFailure(error))
      }
    }

    void start()
    return () => {
      current = false
      controller.abort()
      if (timer !== undefined) clearTimeout(timer)
    }
  }, [api, random, state, testId])

  useEffect(() => {
    if (state.kind !== 'submitting') return

    const controller = new AbortController()
    let current = true
    void api
      .submit(testId, state.payload, controller.signal)
      .then((result) => {
        if (!current) return
        if (result.status === 'active') {
          setState({ kind: 'question', question: result.question, selection: null })
        } else {
          setState({
            kind: 'completed',
            feedback: result.feedback,
            questionResults: result.question_results,
          })
        }
      })
      .catch((error: unknown) => {
        if (!current || isAborted(error)) return
        setState(submissionFailure(error, state))
      })

    return () => {
      current = false
      controller.abort()
    }
  }, [api, state, testId])

  const submit = () => {
    if (state.kind !== 'question' || state.selection === null) return
    const payload = {
      submission_id: state.question.submission_id,
      option_id: state.selection,
    }
    setState({
      kind: 'submitting',
      question: state.question,
      selection: state.selection,
      payload,
      requestKey: 0,
    })
  }

  const recover = () => {
    if (state.kind !== 'failed' || state.recovery === undefined) return
    if (state.recovery.kind === 'retry_submission') {
      setState({
        kind: 'submitting',
        question: state.recovery.question,
        selection: state.recovery.selection,
        payload: state.recovery.payload,
        requestKey: 1,
      })
      return
    }
    setState({ kind: 'preparing', requestKey: 1 })
  }

  return (
    <main className="player-shell">
      <header className="brand" aria-label="Õpiraja hindamine">
        <span className="brand-mark" aria-hidden="true">Õ</span>
        <span>Õpiraja test</span>
      </header>

      <section className="player-card">
        {state.kind === 'welcome' && (
          <WelcomeScreen
            onStart={() => setState({ kind: 'preparing', requestKey: 0 })}
          />
        )}

        {state.kind === 'preparing' && (
          <StatusPanel title="Valmistame testi ette">
            <p role="status" aria-live="polite">
              Testi kavandatakse. See võib võtta veidi aega…
            </p>
          </StatusPanel>
        )}

        {(state.kind === 'question' || state.kind === 'submitting') && (
          <QuestionView
            question={state.question}
            selection={state.selection}
            submitting={state.kind === 'submitting'}
            onSelect={(selection) => {
              if (state.kind === 'question') {
                setState({ ...state, selection })
              }
            }}
            onSubmit={submit}
          />
        )}

        {state.kind === 'completed' && (
          <Feedback
            feedback={state.feedback}
            questionResults={state.questionResults}
          />
        )}

        {state.kind === 'failed' && (
          <FailurePanel state={state} onRecover={recover} />
        )}
      </section>
    </main>
  )
}

function WelcomeScreen({ onStart }: { onStart: () => void }) {
  const [showInfo, setShowInfo] = useState(false)
  const infoButtonRef = useRef<HTMLButtonElement>(null)

  useEffect(() => {
    if (!showInfo) return

    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        setShowInfo(false)
        infoButtonRef.current?.focus()
      }
    }
    document.addEventListener('keydown', closeOnEscape)
    return () => document.removeEventListener('keydown', closeOnEscape)
  }, [showInfo])

  const closeInfo = () => {
    setShowInfo(false)
    window.requestAnimationFrame(() => infoButtonRef.current?.focus())
  }

  return (
    <div className="welcome-screen">
      <button
        ref={infoButtonRef}
        className="info-button"
        type="button"
        aria-label="Testi info"
        aria-haspopup="dialog"
        onClick={() => setShowInfo(true)}
      >
        <span aria-hidden="true">i</span>
      </button>
      <div className="welcome-content">
        <p className="eyebrow">Tere tulemast</p>
        <h1>Õpiraja test</h1>
        <p className="welcome-intro">
          Test aitab leida, mida sa juba oskad ja milliste teemadega võiksid
          järgmisena edasi liikuda.
        </p>
        <button type="button" onClick={onStart}>Alusta testi</button>
      </div>

      {showInfo && (
        <div className="modal-backdrop" onMouseDown={(event) => {
          if (event.target === event.currentTarget) closeInfo()
        }}>
          <section
            className="info-modal"
            role="dialog"
            aria-modal="true"
            aria-labelledby="test-info-title"
          >
            <button
              className="modal-close"
              type="button"
              aria-label="Sulge testi info"
              autoFocus
              onClick={closeInfo}
            >
              <span aria-hidden="true">×</span>
            </button>
            <p className="eyebrow">Testi tutvustus</p>
            <h2 id="test-info-title">Kuidas test töötab?</h2>
            <div className="info-copy">
              {/* Replace this sample copy with the final test information. */}
              <p>
                Test kohandub sinu vastuste järgi: järgmine küsimus valitakse
                selle põhjal, milliseid teadmisi sinu senised vastused näitavad.
              </p>
              <p>
                Vasta igale küsimusele iseseisvalt ja vali enda arvates parim
                vastus. Testiseanss kestab ligikaudu 10–15 minutit ning lõpus
                kuvatakse sulle personaalne tagasiside.
              </p>
            </div>
          </section>
        </div>
      )}
    </div>
  )
}

function InvalidLink() {
  return (
    <main className="player-shell">
      <section className="player-card centered-message" role="alert">
        <p className="eyebrow">Õpiraja test</p>
        <h1>Testi link ei ole kehtiv</h1>
        <p>Kontrolli linki ja proovi uuesti.</p>
      </section>
    </main>
  )
}

function StatusPanel({
  title,
  children,
}: {
  title: string
  children: React.ReactNode
}) {
  return (
    <div className="centered-message">
      <div className="spinner" aria-hidden="true" />
      <p className="eyebrow">Palun oota</p>
      <h1>{title}</h1>
      {children}
    </div>
  )
}

function QuestionView({
  question,
  selection,
  submitting,
  onSelect,
  onSubmit,
}: {
  question: PlayerQuestion
  selection: string | null
  submitting: boolean
  onSelect: (selection: string) => void
  onSubmit: () => void
}) {
  return (
    <form
      onSubmit={(event) => {
        event.preventDefault()
        onSubmit()
      }}
    >
      <p className="eyebrow">Küsimus</p>
      {question.instruction && (
        <p className="instruction">{question.instruction}</p>
      )}
      {question.stimulus && <div className="stimulus">{question.stimulus}</div>}
      <fieldset disabled={submitting}>
        <legend>{question.prompt}</legend>
        <div className="options">
          {question.options.map((option) => (
            <label className="option" key={option.id}>
              <input
                type="radio"
                name="answer"
                value={option.id}
                checked={selection === option.id}
                onChange={() => onSelect(option.id)}
              />
              <span>{option.text}</span>
            </label>
          ))}
        </div>
      </fieldset>
      {submitting && (
        <p className="submit-status" role="status" aria-live="polite">
          Vastust salvestatakse…
        </p>
      )}
      <div className="actions">
        <button type="submit" disabled={selection === null || submitting}>
          {submitting ? 'Saadan…' : 'Edasi'}
        </button>
      </div>
    </form>
  )
}

function Feedback({
  feedback,
  questionResults,
}: {
  feedback: PlayerFeedback
  questionResults: PlayerQuestionResult[]
}) {
  return (
    <div className="feedback">
      <p className="eyebrow">Test on lõpetatud, võid selle akna sulgeda.</p>
      <h1>Sinu tagasiside</h1>
      {feedback.summary !== null && <p className="summary">{feedback.summary}</p>}
      {feedback.confidence_limited && (
        <p className="confidence-note">
          See test ei suutnud sinu teadmisi antud teemal piisavalt kindlalt
          eristada. Soovitatav on hiljem uuesti testida.
        </p>
      )}
      <div className="feedback-grid">
        <FeedbackSection
          tone="mastered"
          title="Juba oskad"
          entries={feedback.already_mastered}
          empty="Sellest testist ei leidnud me veel midagi kindlalt kinnitatut."
        />
        <FeedbackSection
          tone="learn"
          title="Võid õppida / rohkem süveneda"
          entries={feedback.learn_next}
          empty="Hetkel pole uut suunda pakkuda."
        />
        <FeedbackSection
          tone="review"
          title="Tasuks korrata"
          entries={feedback.review}
          empty="Midagi kindlat kordamist ei vaja."
        />
      </div>
      {questionResults.length > 0 && (
        <QuestionResults results={questionResults} />
      )}
    </div>
  )
}

function QuestionResults({ results }: { results: PlayerQuestionResult[] }) {
  return (
    <details className="question-results">
      <summary>Näita küsimusi ja vastuseid</summary>
      <div className="question-results-scroll">
        <table>
          <caption className="visually-hidden">
            Küsimuste ja vastuste tulemused
          </caption>
          <thead>
            <tr>
              <th scope="col">Küsimus</th>
              <th scope="col">Sinu vastus</th>
              <th scope="col">Õige vastus</th>
            </tr>
          </thead>
          <tbody>
            {results.map((result) => (
              <tr
                className={result.is_correct ? 'correct' : 'incorrect'}
                key={result.item_id}
              >
                <td>
                  <span className="visually-hidden">
                    {result.is_correct ? 'Õige vastus. ' : 'Vale vastus. '}
                  </span>
                  <ResultQuestion result={result} />
                </td>
                <td>{result.student_answer}</td>
                <td>{result.correct_answer}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </details>
  )
}

const STIMULUS_PREVIEW_LENGTH = 110
const PROMPT_PREVIEW_LENGTH = 160

function ResultQuestion({ result }: { result: PlayerQuestionResult }) {
  const [expanded, setExpanded] = useState(false)
  const contentId = useId()
  const stimulusIsLong =
    result.stimulus !== null &&
    Array.from(result.stimulus).length > STIMULUS_PREVIEW_LENGTH
  const promptIsLong = Array.from(result.prompt).length > PROMPT_PREVIEW_LENGTH
  const canExpand = stimulusIsLong || promptIsLong
  const stimulus =
    result.stimulus === null || expanded
      ? result.stimulus
      : truncateText(result.stimulus, STIMULUS_PREVIEW_LENGTH)
  const prompt = expanded
    ? result.prompt
    : truncateText(result.prompt, PROMPT_PREVIEW_LENGTH)

  return (
    <div className="result-question">
      <div id={contentId} className="result-question-copy">
        {stimulus !== null && (
          <p className="result-question-stimulus">{stimulus}</p>
        )}
        <p className="result-question-prompt">{prompt}</p>
      </div>
      {canExpand && (
        <button
          className="question-text-toggle"
          type="button"
          aria-controls={contentId}
          aria-expanded={expanded}
          onClick={() => setExpanded((current) => !current)}
        >
          {expanded ? 'Peida kogu küsimus' : 'Näita kogu küsimust'}
        </button>
      )}
    </div>
  )
}

function truncateText(value: string, maximumLength: number): string {
  const characters = Array.from(value)
  if (characters.length <= maximumLength) return value
  return `${characters.slice(0, maximumLength).join('').trimEnd()}…`
}

function FeedbackSection({
  title,
  entries,
  empty,
  tone,
}: {
  title: string
  entries: string[]
  empty: string
  tone: 'mastered' | 'learn' | 'review'
}) {
  return (
    <section className={`feedback-section ${tone}`}>
      <h2>{title}</h2>
      {entries.length > 0 ? (
        <ul>
          {entries.map((entry) => <li key={entry}>{entry}</li>)}
        </ul>
      ) : (
        <p className="empty-feedback">{empty}</p>
      )}
    </section>
  )
}

function FailurePanel({
  state,
  onRecover,
}: {
  state: Extract<PlayerState, { kind: 'failed' }>
  onRecover: () => void
}) {
  return (
    <div className="centered-message" role="alert">
      <p className="eyebrow">Midagi läks valesti</p>
      <h1>{state.message}</h1>
      {state.requestId && (
        <p className="request-id">Viitenumber: {state.requestId}</p>
      )}
      {state.recovery && (
        <button type="button" onClick={onRecover}>
          {state.recovery.kind === 'reload_start'
            ? 'Laadi test uuesti'
            : 'Proovi uuesti'}
        </button>
      )}
    </div>
  )
}

function startFailure(error: unknown): Extract<PlayerState, { kind: 'failed' }> {
  const apiError = asApiError(error)
  if (apiError?.kind === 'unauthorized') {
    return failed('Testi link on aegunud.', apiError)
  }
  if (apiError?.kind === 'forbidden') {
    return failed('Seda testi ei saa avada.', apiError)
  }
  if (apiError?.kind === 'not_found') {
    return failed('Testi ei leitud.', apiError)
  }
  if (apiError?.kind === 'validation') {
    return failed('Testi link ei ole kehtiv.', apiError)
  }
  if (apiError?.kind === 'conflict') {
    return failed('Testi olekut tuleb uuendada.', apiError, {
      kind: 'reload_start',
    })
  }
  return failed('Testi laadimine ebaõnnestus.', apiError, {
    kind: 'retry_start',
  })
}

function submissionFailure(
  error: unknown,
  state: Extract<PlayerState, { kind: 'submitting' }>,
): Extract<PlayerState, { kind: 'failed' }> {
  const apiError = asApiError(error)
  if (apiError?.kind === 'unauthorized') {
    return failed('Testi link on aegunud.', apiError)
  }
  if (apiError?.kind === 'conflict') {
    return failed('Testi olek on muutunud.', apiError, {
      kind: 'reload_start',
    })
  }
  if (apiError?.kind === 'forbidden') {
    return failed('Vastust ei saa saata.', apiError)
  }
  if (apiError?.kind === 'not_found') {
    return failed('Testi ei leitud.', apiError)
  }
  if (apiError?.kind === 'validation') {
    return failed('Vastust ei saa saata.', apiError)
  }
  return failed('Vastuse saatmine ebaõnnestus.', apiError, {
    kind: 'retry_submission',
    question: state.question,
    selection: state.selection,
    payload: state.payload,
  })
}

function failed(
  message: string,
  error: PlayerApiError | null,
  recovery?: Recovery,
): Extract<PlayerState, { kind: 'failed' }> {
  return {
    kind: 'failed',
    message,
    requestId: error?.requestId ?? null,
    ...(recovery ? { recovery } : {}),
  }
}

function asApiError(error: unknown): PlayerApiError | null {
  return error instanceof PlayerApiError ? error : null
}

function isAborted(error: unknown): boolean {
  return error instanceof PlayerApiError && error.kind === 'aborted'
}

export default App
