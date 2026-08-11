import type { AnchorHTMLAttributes, ButtonHTMLAttributes, ReactNode } from 'react'
import styles from './Button.module.css'

type Variant = 'primary' | 'secondary' | 'tertiary' | 'icon'
type CommonProps = { variant?: Variant; leadingIcon?: ReactNode }

export function Button({ variant = 'primary', leadingIcon, className, children, ...props }: ButtonHTMLAttributes<HTMLButtonElement> & CommonProps) {
  return <button {...props} className={[styles.button, styles[variant], className].filter(Boolean).join(' ')}>{leadingIcon}{children}</button>
}

export function ButtonLink({ variant = 'tertiary', leadingIcon, className, children, ...props }: AnchorHTMLAttributes<HTMLAnchorElement> & CommonProps) {
  return <a {...props} className={[styles.button, styles[variant], className].filter(Boolean).join(' ')}>{leadingIcon}{children}</a>
}
