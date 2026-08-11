import { useEffect, useRef } from 'react'
import type { ReactNode } from 'react'
import styles from './Dialog.module.css'

type Props = {
  open: boolean
  title: string
  children: ReactNode
  onClose: () => void
}

export function Dialog({ open, title, children, onClose }: Props) {
  const dialogRef = useRef<HTMLDialogElement>(null)
  const triggerRef = useRef<HTMLElement | null>(null)

  useEffect(() => {
    const dialog = dialogRef.current
    if (!dialog) return
    const isOpen = dialog.open || dialog.hasAttribute('open')
    if (open && !isOpen) {
      triggerRef.current = document.activeElement instanceof HTMLElement ? document.activeElement : null
      if (typeof dialog.showModal === 'function') dialog.showModal()
      else dialog.setAttribute('open', '')
    }
    if (!open && isOpen) {
      if (typeof dialog.close === 'function') dialog.close()
      else dialog.removeAttribute('open')
    }
    return () => {
      if (dialog.open || dialog.hasAttribute('open')) {
        if (typeof dialog.close === 'function') dialog.close()
        else dialog.removeAttribute('open')
      }
    }
  }, [open])

  function close() {
    onClose()
    queueMicrotask(() => triggerRef.current?.focus())
  }

  return (
    <dialog ref={dialogRef} className={styles.dialog} aria-labelledby="dialog-title" onCancel={(event) => { event.preventDefault(); close() }} onClose={close}>
      <div className={styles.content}>
        <h2 id="dialog-title" className={styles.visuallyHidden}>{title}</h2>
        {children}
      </div>
    </dialog>
  )
}
