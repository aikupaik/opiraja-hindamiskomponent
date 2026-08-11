import type { HTMLAttributes } from 'react'
import styles from './PageContainer.module.css'

export function PageContainer({ className, ...props }: HTMLAttributes<HTMLElement>) {
  return <main {...props} className={[styles.page, className].filter(Boolean).join(' ')} />
}
