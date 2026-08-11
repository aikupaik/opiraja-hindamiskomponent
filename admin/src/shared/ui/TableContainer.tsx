import type { HTMLAttributes } from 'react'
import styles from './TableContainer.module.css'

export function TableContainer({ className, ...props }: HTMLAttributes<HTMLDivElement>) {
  return <div {...props} className={[styles.container, className].filter(Boolean).join(' ')} />
}
