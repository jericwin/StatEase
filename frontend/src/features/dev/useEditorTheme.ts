import { EditorView } from '@codemirror/view'
import { HighlightStyle, syntaxHighlighting } from '@codemirror/language'
import { tags as t } from '@lezer/highlight'
import { useEffect, useState } from 'react'

function isDark() {
  return document.documentElement.classList.contains('dark')
}

/** Editor theme built from the app's design tokens so it follows light/dark mode. */
export function useEditorTheme() {
  const [dark, setDark] = useState(isDark)
  useEffect(() => {
    const h = () => setDark(isDark())
    window.addEventListener('statease:theme', h)
    return () => window.removeEventListener('statease:theme', h)
  }, [])
  const base = EditorView.theme(
    {
      '&': { backgroundColor: 'var(--surface)', color: 'var(--text)', height: '100%', fontSize: '13px' },
      '.cm-content': { fontFamily: 'IBM Plex Mono, ui-monospace, monospace', caretColor: 'var(--accent)' },
      '.cm-gutters': { backgroundColor: 'var(--surface-2)', color: 'var(--muted)', borderRight: '1px solid var(--border)' },
      '.cm-activeLine': { backgroundColor: 'color-mix(in srgb, var(--accent-soft) 60%, transparent)' },
      '.cm-activeLineGutter': { backgroundColor: 'var(--surface-3)' },
      '&.cm-focused .cm-selectionBackground, .cm-selectionBackground, ::selection': { backgroundColor: 'color-mix(in srgb, var(--accent) 25%, transparent) !important' },
      '.cm-tooltip': { backgroundColor: 'var(--surface)', border: '1px solid var(--border)', color: 'var(--text)' },
      '.cm-tooltip-autocomplete > ul > li[aria-selected]': { backgroundColor: 'var(--accent-soft)', color: 'var(--text)' },
      '&.cm-focused': { outline: 'none' },
    },
    { dark },
  )
  const highlight = HighlightStyle.define([
    { tag: [t.keyword, t.operatorKeyword, t.modifier], color: dark ? '#86afe8' : '#1d4f91', fontWeight: '500' },
    { tag: [t.string, t.special(t.string)], color: dark ? '#9fd3a8' : '#2f6b48' },
    { tag: [t.number, t.bool, t.null], color: dark ? '#e0a94a' : '#8a5300' },
    { tag: [t.comment, t.lineComment, t.blockComment], color: 'var(--muted)', fontStyle: 'italic' },
    { tag: [t.function(t.variableName), t.standard(t.name)], color: dark ? '#c5a5e8' : '#6a3d9a' },
    { tag: [t.typeName, t.className], color: dark ? '#6cbfd9' : '#1f6f8b' },
    { tag: [t.definition(t.variableName), t.propertyName], color: 'var(--text)' },
  ])
  return [base, syntaxHighlighting(highlight)]
}
