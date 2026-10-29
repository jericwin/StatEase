import { cn } from '@/lib/utils'

const BODY =
  'M0.5 23.7L0.5 21.8L1.0 21.4L1.6 20.9L2.1 20.3L2.7 19.7L3.2 19.0L3.8 18.2L4.3 17.3L4.9 16.4L5.4 15.3L6.0 14.3L6.5 13.2L7.1 12.1L7.6 11.0L8.2 9.9L8.7 8.8L9.3 7.8L9.8 6.9L10.4 6.1L10.9 5.4L11.5 4.8L12.0 4.5L12.6 4.2L13.1 4.2L13.7 4.3L14.2 4.6L14.8 5.1L15.3 5.7L15.9 6.5L16.4 7.3L17.0 8.3L17.0 23.7Z'
const TAIL =
  'M18.3 23.7L18.3 10.8L19.4 13.1L20.5 15.2L21.6 17.2L22.7 18.9L23.8 20.2L24.9 21.3L26.0 22.1L27.1 22.7L28.2 23.1L29.3 23.3L30.4 23.5L31.5 23.6L31.5 23.7Z'

/**
 * The StatEase mark: a normal curve on a baseline with the upper tail set apart —
 * the region a significance test looks at. Two colours: the body takes `currentColor`,
 * the tail takes `tailClassName` (rust by default).
 */
export function Mark({ className, tailClassName = 'fill-rust' }: { className?: string; tailClassName?: string }) {
  return (
    <svg viewBox="0 0 32 32" className={cn('size-7 shrink-0', className)} aria-hidden>
      <path d={BODY} fill="currentColor" />
      <path d={TAIL} className={tailClassName} />
      <rect x="0.5" y="25.2" width="31" height="2.6" rx="1.3" fill="currentColor" />
    </svg>
  )
}

export const MARK_PATHS = { body: BODY, tail: TAIL }
