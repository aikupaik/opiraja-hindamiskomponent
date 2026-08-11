import type { ReactNode } from 'react'
import styles from './EmptyState.module.css'

export function EmptyState({ title, children }: { title: string; children?: ReactNode }) {
  return <section className={styles.empty}><h2>{title}</h2>{children && <p>{children}</p>}</section>
}
