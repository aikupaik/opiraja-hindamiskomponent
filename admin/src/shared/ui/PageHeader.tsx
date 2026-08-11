import type { ReactNode } from 'react'
import styles from './PageHeader.module.css'

export function PageHeader({ eyebrow, title, description, actions }: { eyebrow?: string; title: string; description?: string; actions?: ReactNode }) {
  return <header className={styles.header}><div>{eyebrow && <p className={styles.eyebrow}>{eyebrow}</p>}<h1>{title}</h1>{description && <p className={styles.description}>{description}</p>}</div>{actions && <div className={styles.actions}>{actions}</div>}</header>
}
