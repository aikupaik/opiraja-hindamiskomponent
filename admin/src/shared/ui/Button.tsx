import type { AnchorHTMLAttributes, ButtonHTMLAttributes, ReactNode } from 'react'
import styles from './Button.module.css'

type Variant = 'primary' | 'secondary' | 'outlined' | 'light' | 'tertiary' | 'danger' | 'icon'
type CommonProps = { variant?: Variant; leadingIcon?: ReactNode; loading?: boolean }

export function Button({ variant = 'primary', leadingIcon, loading = false, className, children, disabled, ...props }: ButtonHTMLAttributes<HTMLButtonElement> & CommonProps) {
  return <button {...props} disabled={disabled || loading} aria-busy={loading || undefined} className={[styles.button, styles[variant], loading && styles.loading, className].filter(Boolean).join(' ')}>{loading ? <span className={styles.spinner} aria-hidden="true" /> : leadingIcon}<span>{children}</span></button>
}

export function ButtonLink({ variant = 'tertiary', leadingIcon, className, children, ...props }: AnchorHTMLAttributes<HTMLAnchorElement> & Omit<CommonProps, 'loading'>) {
  return <a {...props} className={[styles.button, styles[variant], className].filter(Boolean).join(' ')}>{leadingIcon}{children}</a>
}
