import type { HTMLAttributes, ReactNode } from 'react'
import styles from './Alert.module.css'

export type StatusTone = 'neutral' | 'running' | 'success' | 'warning' | 'error'

export function Alert({ tone = 'neutral', children, ...props }: HTMLAttributes<HTMLDivElement> & { tone?: StatusTone; children: ReactNode }) {
  return <div {...props} className={`${styles.alert} ${styles[tone]}`} role={tone === 'error' ? 'alert' : 'status'} aria-live="polite">{children}</div>
}

export function StatusChip({ tone = 'neutral', children }: { tone?: StatusTone; children: ReactNode }) {
  return <span className={`${styles.chip} ${styles[tone]}`}>{children}</span>
}
