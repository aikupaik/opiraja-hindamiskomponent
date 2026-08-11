import type { InputHTMLAttributes, ReactNode, SelectHTMLAttributes, TextareaHTMLAttributes } from 'react'
import styles from './FormField.module.css'

type FieldProps = { label: string; hint?: ReactNode; error?: string; children: ReactNode }

export function FormField({ label, hint, error, children }: FieldProps) {
  return <label className={styles.field}><span>{label}</span>{children}{hint && <small>{hint}</small>}{error && <small className={styles.error} role="alert">{error}</small>}</label>
}

export function TextInput(props: InputHTMLAttributes<HTMLInputElement>) { return <input {...props} className={[styles.control, props.className].filter(Boolean).join(' ')} /> }
export function TextArea(props: TextareaHTMLAttributes<HTMLTextAreaElement>) { return <textarea {...props} className={[styles.control, props.className].filter(Boolean).join(' ')} /> }
export function Select(props: SelectHTMLAttributes<HTMLSelectElement>) { return <select {...props} className={[styles.control, props.className].filter(Boolean).join(' ')} /> }
