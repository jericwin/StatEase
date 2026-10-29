import { clsx, type ClassValue } from 'clsx'
import { useSyncExternalStore } from 'react'
import { twMerge } from 'tailwind-merge'

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}

export function storageGet(key: string, fallback: string): string {
  try {
    return localStorage.getItem(key) ?? fallback
  } catch {
    return fallback
  }
}

export function storageSet(key: string, value: string) {
  try {
    localStorage.setItem(key, value)
  } catch {
    /* storage unavailable (private mode) */
  }
}

export type Theme = 'system' | 'light' | 'dark'

export function applyTheme(theme: Theme) {
  const dark = theme === 'dark' || (theme === 'system' && window.matchMedia('(prefers-color-scheme: dark)').matches)
  document.documentElement.classList.toggle('dark', dark)
  storageSet('statease.theme', theme)
  window.dispatchEvent(new CustomEvent('statease:theme'))
}

export function asArray(v: string | string[] | undefined | null): string[] {
  if (!v) return []
  return Array.isArray(v) ? v : [v]
}

/** True while the media query matches; re-renders on change. */
export function useMediaQuery(query: string): boolean {
  return useSyncExternalStore(
    (cb) => {
      const mq = window.matchMedia(query)
      mq.addEventListener('change', cb)
      return () => mq.removeEventListener('change', cb)
    },
    () => window.matchMedia(query).matches,
    () => false,
  )
}
