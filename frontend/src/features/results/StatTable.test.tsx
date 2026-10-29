import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import type { ResultTable } from '@/lib/types'
import { StatTable } from './StatTable'

const table: ResultTable = {
  id: 'main',
  kind: 'main',
  title: 'Independent-Samples t-Test',
  columns: [
    { key: 'test', label: 'Test', fmt: 'text' },
    { key: 't', label: 't', fmt: 'stat', group: 'statistic' },
    { key: 'df', label: 'df', fmt: 'num', group: 'df' },
    { key: 'p', label: 'p', fmt: 'p', group: 'p' },
    { key: 'empty', label: 'Never filled', fmt: 'num' },
  ],
  rows: [
    { test: 'Welch', t: -4.06213, df: 17.776, p: 0.00002 },
    { test: 'Student', t: -1.86081, df: 18, p: 0.07919 },
  ],
  notes: ['Mean difference = A − B.'],
}

describe('StatTable', () => {
  it('renders APA-formatted values and table number', () => {
    render(<StatTable table={table} decimals={2} style="apa" alpha={0.05} number={3} />)
    expect(screen.getByText('Table 3.')).toBeInTheDocument()
    expect(screen.getByText('-4.06')).toBeInTheDocument()
    expect(screen.getByText('.079')).toBeInTheDocument()
    expect(screen.getByText(/< \.001/)).toBeInTheDocument()
  })

  it('marks significance with text, not only colour or weight', () => {
    render(<StatTable table={table} decimals={2} style="apa" alpha={0.05} />)
    expect(screen.getAllByText('(significant)')).toHaveLength(1)
  })

  it('hides columns that have no values', () => {
    render(<StatTable table={table} decimals={2} style="apa" alpha={0.05} />)
    expect(screen.queryByText('Never filled')).not.toBeInTheDocument()
    expect(screen.getByText(/Mean difference/)).toBeInTheDocument()
  })
})
