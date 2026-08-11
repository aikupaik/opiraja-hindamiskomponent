import type { SVGProps } from 'react'

type IconProps = SVGProps<SVGSVGElement> & { title?: string }
function Icon({ title, children, ...props }: IconProps) { return <svg viewBox="0 0 24 24" width="1em" height="1em" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden={title ? undefined : true} role={title ? 'img' : undefined} {...props}>{title && <title>{title}</title>}{children}</svg> }
export function LockIcon(props: IconProps) { return <Icon {...props}><rect x="5" y="10" width="14" height="10" rx="2" /><path d="M8 10V7a4 4 0 0 1 8 0v3" /></Icon> }
export function ChevronRightIcon(props: IconProps) { return <Icon {...props}><path d="m9 18 6-6-6-6" /></Icon> }
export function CloseIcon(props: IconProps) { return <Icon {...props}><path d="m6 6 12 12M18 6 6 18" /></Icon> }
