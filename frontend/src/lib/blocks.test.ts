import { describe, expect, it } from 'vitest'
import { chartNames, MANUAL_NOTE, resolveChart, resolveTable } from './blocks'
import type { ChartSpec, ResultTable } from './types'

// Same cases as backend/tests/test_reports.py::test_block_edit_rules — preview and export must agree.
const table: ResultTable = {
  id: 'main',
  kind: 'main',
  title: 'T',
  columns: [
    { key: 'a', label: 'A', fmt: 'text' },
    { key: 'x', label: 'X', fmt: 'num', group: 'statistic' },
    { key: 'p', label: 'p', fmt: 'p', group: 'p' },
  ],
  rows: [
    { a: 'r1', x: 1, p: 0.01 },
    { a: 'r2', x: 2, p: 0.2 },
  ],
  notes: [],
}

describe('resolveTable', () => {
  it('reorders, renames, hides detail columns and appends manual rows', () => {
    const out = resolveTable(table, { columns: [{ key: 'p' }, { key: 'a', label: 'Row' }, { key: 'm_1', label: 'Note', manual: true }], hidden_rows: [1], extra_rows: [{ a: 'added' }] }, true)
    expect(out.columns.map((c) => c.key)).toEqual(['p', 'a', 'm_1'])
    expect(out.columns[1].label).toBe('Row')
    expect(out.rows.map((r) => r.a)).toEqual(['r1', 'added'])
    expect(out.rows[1]._manual).toBeTruthy()
    expect(out.notes).toContain(MANUAL_NOTE)
  })

  it('flags manual cells and leaves computed values untouched', () => {
    const out = resolveTable(table, { cells: { '0:x': 9 } })
    expect(out.rows[0].x).toBe(9)
    expect(out.rows[0]._manual).toEqual(['x'])
    expect(out.rows[1].x).toBe(2)
    expect(table.rows[0].x).toBe(1) // source never mutated
  })

  it('drops edits for columns the analysis no longer produces', () => {
    const out = resolveTable(table, { columns: [{ key: 'gone', label: 'Old' }, { key: 'a' }] })
    expect(out.columns.map((c) => c.key)).toEqual(['a', 'x', 'p'])
  })
})

const chart: ChartSpec = {
  id: 'means', type: 'meanci', title: 'M', x_label: '', y_label: 'Score', caption: '', note: null,
  data: { groups: [{ name: 'F1', mean: 5, lower: 4, upper: 6 }, { name: 'F2', mean: 7, lower: 6, upper: 8 }] },
}

describe('resolveChart', () => {
  it('reorders and relabels groups', () => {
    const c = resolveChart(chart, { order: ['F2', 'F1'], labels: { F1: 'Formulation 1' } })
    expect((c.data.groups as { name: string }[]).map((g) => g.name)).toEqual(['F2', 'Formulation 1'])
  })
  it('converts type and hides groups consistently', () => {
    const c = resolveChart(chart, { type: 'means', hidden: ['F1'] })
    expect(c.type).toBe('means')
    expect(c.data.categories).toEqual(['F2'])
    expect((c.data.series as { values: number[] }[])[0].values).toEqual([7])
  })
  it('applies title and axis labels', () => {
    const c = resolveChart(chart, { y_label: 'Mean score' }, 'Figure title')
    expect(c.title).toBe('Figure title')
    expect(c.y_label).toBe('Mean score')
    expect(chartNames(chart).groups).toEqual(['F1', 'F2'])
  })
})
