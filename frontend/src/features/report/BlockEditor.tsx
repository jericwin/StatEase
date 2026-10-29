import { ArrowDown, ArrowUp, Eye, EyeOff, Plus, RefreshCw, RotateCcw, Trash2, X } from 'lucide-react'
import { useMemo, useState } from 'react'
import { Button } from '@/components/ui/button'
import { Callout, Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/feedback'
import { Field, Input, Select, Switch, Textarea } from '@/components/ui/form'
import { RoleSlot } from '@/features/analysis/RoleSlot'
import { CHART_STYLE_LABEL, chartNames, chartStyles, chartTypes, defaultStyle, MANUAL_NOTE, resolveChart, type ChartEdits, type ColumnEdit, type TableEdits } from '@/lib/blocks'
import type { AnalysisSpec, Assignment, Dataset, ReportBlock } from '@/lib/types'
import { asArray, cn } from '@/lib/utils'

const CHART_TYPE_LABEL: Record<string, string> = { meanci: 'Means with CI (points)', means: 'Bar chart with CI', bar: 'Bar chart', box: 'Box plot', histogram: 'Histogram', scatter: 'Scatter plot', qq: 'Q–Q plot', heatmap: 'Heatmap', interaction: 'Line chart' }

export interface RebindRequest {
  variables?: Assignment
  filter?: { column: string; values: string[] } | null
  chart_id?: string
}

function move<T>(arr: T[], i: number, d: number): T[] {
  const j = i + d
  if (j < 0 || j >= arr.length) return arr
  const next = [...arr]
  ;[next[i], next[j]] = [next[j], next[i]]
  return next
}

function categories(dataset: Dataset, name: string): string[] {
  const v = dataset.variables.find((x) => x.name === name)
  const key = (x: string | number) => String(x)
  return (v?.profile.categories ?? []).map((c) => v?.category_labels[key(c.value)] ?? key(c.value))
}

/** Which data the block shows: groups (row filter) and variables. Changing it recomputes from the dataset. */
function ScopeEditor({ block, dataset, spec, onRebind, busy }: { block: ReportBlock; dataset: Dataset; spec?: AnalysisSpec; onRebind: (r: RebindRequest) => void; busy: boolean }) {
  const a = block.analysis!
  const groupers = dataset.variables.filter((v) => ['nominal', 'binary', 'ordinal'].includes(v.level) && (v.profile.unique ?? 0) >= 2 && (v.profile.unique ?? 0) <= 20)
  const usesGroupRole = spec?.roles.some((r) => ['group', 'factor', 'rows', 'columns'].includes(r.key)) ?? false
  const [column, setColumn] = useState(a.filter?.column ?? (usesGroupRole ? '' : ''))
  const [values, setValues] = useState<string[]>(a.filter?.values ?? [])
  const [vars, setVars] = useState<Assignment>(a.variables ?? {})
  const cats = column ? categories(dataset, column) : []
  const dirty = JSON.stringify(vars) !== JSON.stringify(a.variables ?? {}) || column !== (a.filter?.column ?? '') || JSON.stringify(values) !== JSON.stringify(a.filter?.values ?? [])

  const apply = () => {
    let variables = vars
    const filter = column && values.length ? { column, values } : null
    if (a.analysis_type === 'descriptives') {
      const v = { ...variables }
      if (filter && values.length > 1) v.split_by = column
      else if (v.split_by === column) delete v.split_by
      if (!filter && v.split_by === a.filter?.column) delete v.split_by
      variables = v
    }
    onRebind({ variables, filter })
  }

  return (
    <div className="space-y-4">
      <p className="text-[13px] text-muted">
        Shows <span className="font-medium text-fg">{a.title}</span>
        {a.heading && <> · {a.heading}</>}. Changing anything here recalculates the statistics from your data.
      </p>
      {groupers.length > 0 && (
        <div className="space-y-2 rounded-md border border-line p-3">
          <Field label="Show results for">
            {(id) => (
              <Select id={id} value={column} onChange={(e) => { setColumn(e.target.value); setValues([]) }}>
                <option value="">All data</option>
                {groupers.map((g) => <option key={g.name} value={g.name}>{g.label || g.name}</option>)}
              </Select>
            )}
          </Field>
          {column && (
            <div className="flex flex-wrap gap-1.5">
              {cats.map((c) => {
                const on = values.includes(c)
                return (
                  <button key={c} type="button" aria-pressed={on} onClick={() => setValues(on ? values.filter((x) => x !== c) : [...values, c])}
                    className={cn('h-7 rounded-full border px-2.5 text-[12.5px]', on ? 'border-accent bg-accent-soft font-medium text-accent' : 'border-line-strong text-fg-2')}>
                    {c}
                  </button>
                )
              })}
            </div>
          )}
          {column && values.length > 1 && a.analysis_type === 'descriptives' && <p className="text-xs text-muted">Selected groups are shown side by side.</p>}
        </div>
      )}
      {spec && (
        <div className="space-y-3">
          {spec.roles.map((role) => {
            const others = new Set(spec.roles.filter((r) => r.key !== role.key).flatMap((r) => asArray(vars[r.key] as string | string[])))
            return (
              <RoleSlot key={role.key} role={role} value={asArray(vars[role.key] as string | string[])} variables={dataset.variables} usedElsewhere={others}
                onChange={(v) => setVars({ ...vars, [role.key]: role.max === 1 ? (v[0] ?? '') : v })} />
            )
          })}
        </div>
      )}
      <Button variant="primary" onClick={apply} loading={busy} disabled={!dirty}>
        <RefreshCw /> Recalculate
      </Button>
      {block.type === 'table' && <p className="text-xs text-muted">Manual cell edits are cleared when the data changes, so no outdated value remains.</p>}
    </div>
  )
}

function TableLayout({ block, onChange }: { block: ReportBlock; onChange: (edits: TableEdits) => void }) {
  const src = block.source_table!
  const edits = (block.edits ?? {}) as TableEdits
  const cols: ColumnEdit[] = useMemo(() => {
    const seen = new Set((edits.columns ?? []).map((c) => c.key))
    return [...(edits.columns ?? []).filter((c) => c.manual || src.columns.some((s) => s.key === c.key)), ...src.columns.filter((c) => !seen.has(c.key)).map((c) => ({ key: c.key }))]
  }, [edits.columns, src.columns])
  const labelOf = (c: ColumnEdit) => c.label || src.columns.find((s) => s.key === c.key)?.label || 'New column'
  const setCols = (next: ColumnEdit[]) => onChange({ ...edits, columns: next })
  const hiddenRows = new Set(edits.hidden_rows ?? [])
  const firstKey = src.columns[0]?.key
  const visibleCols = cols.filter((c) => !c.hidden)
  const [editingCells, setEditingCells] = useState(false)

  return (
    <div className="space-y-5">
      <section>
        <h3 className="label-caps mb-2">Columns</h3>
        <ul className="space-y-1.5">
          {cols.map((c, i) => (
            <li key={c.key} className="flex items-center gap-1.5">
              <Input value={labelOf(c)} onChange={(e) => setCols(cols.map((x) => (x.key === c.key ? { ...x, label: e.target.value } : x)))} className={cn('h-7', c.hidden && 'opacity-50')} aria-label={`Column name ${labelOf(c)}`} />
              <button className="rounded p-1 text-muted hover:text-fg" onClick={() => setCols(cols.map((x) => (x.key === c.key ? { ...x, hidden: !x.hidden } : x)))} aria-label={c.hidden ? 'Show column' : 'Hide column'}>
                {c.hidden ? <EyeOff className="size-4" /> : <Eye className="size-4" />}
              </button>
              <button className="rounded p-1 text-muted hover:text-fg disabled:opacity-30" disabled={i === 0} onClick={() => setCols(move(cols, i, -1))} aria-label="Move column left"><ArrowUp className="size-4" /></button>
              <button className="rounded p-1 text-muted hover:text-fg disabled:opacity-30" disabled={i === cols.length - 1} onClick={() => setCols(move(cols, i, 1))} aria-label="Move column right"><ArrowDown className="size-4" /></button>
              {c.manual && <button className="rounded p-1 text-muted hover:text-danger" onClick={() => setCols(cols.filter((x) => x.key !== c.key))} aria-label="Remove column"><Trash2 className="size-4" /></button>}
            </li>
          ))}
        </ul>
        <Button size="sm" variant="ghost" className="mt-2" onClick={() => setCols([...cols, { key: `m_${Date.now().toString(36)}`, label: 'Notes', manual: true }])}><Plus /> Add column</Button>
      </section>
      <section>
        <h3 className="label-caps mb-2">Rows</h3>
        <ul className="space-y-1">
          {src.rows.map((r, i) => (
            <li key={i} className="flex items-center gap-2 text-[13px]">
              <button className="rounded p-1 text-muted hover:text-fg" onClick={() => {
                const next = new Set(hiddenRows)
                if (next.has(i)) next.delete(i)
                else next.add(i)
                onChange({ ...edits, hidden_rows: [...next] })
              }} aria-label={hiddenRows.has(i) ? 'Show row' : 'Hide row'}>
                {hiddenRows.has(i) ? <EyeOff className="size-4" /> : <Eye className="size-4" />}
              </button>
              <span className={cn('truncate', hiddenRows.has(i) && 'text-muted line-through')}>{String(r[firstKey] ?? `Row ${i + 1}`)}{r.group ? ` · ${String(r.group)}` : ''}</span>
            </li>
          ))}
          {(edits.extra_rows ?? []).map((r, i) => (
            <li key={`x${i}`} className="flex items-center gap-2 text-[13px]">
              <button className="rounded p-1 text-muted hover:text-danger" onClick={() => onChange({ ...edits, extra_rows: (edits.extra_rows ?? []).filter((_, j) => j !== i) })} aria-label="Remove added row"><X className="size-4" /></button>
              <span className="truncate">{String(r[firstKey] ?? 'Added row')} <span className="text-warning">†</span></span>
            </li>
          ))}
        </ul>
        <Button size="sm" variant="ghost" className="mt-2" onClick={() => onChange({ ...edits, extra_rows: [...(edits.extra_rows ?? []), { [firstKey]: 'New row' }] })}><Plus /> Add row</Button>
      </section>
      <section>
        <div className="mb-2 flex items-center justify-between">
          <h3 className="label-caps">Cell values</h3>
          <Switch checked={editingCells} onCheckedChange={setEditingCells} aria-label="Edit cell values" />
        </div>
        {editingCells && (
          <>
            <Callout tone="warning">Values you type are marked with † in the report and are not calculated by StatEase. {MANUAL_NOTE.slice(2)}</Callout>
            <div className="scroll-thin mt-2 max-h-72 overflow-auto rounded-md border border-line">
              <table className="text-[12px]">
                <thead className="sticky top-0 bg-surface-2"><tr>{visibleCols.map((c) => <th key={c.key} className="border-b border-line px-1.5 py-1 text-left font-medium whitespace-nowrap">{labelOf(c)}</th>)}</tr></thead>
                <tbody>
                  {src.rows.map((r, i) => hiddenRows.has(i) ? null : (
                    <tr key={i}>
                      {visibleCols.map((c) => {
                        const k = `${i}:${c.key}`
                        const overridden = edits.cells && k in edits.cells
                        const value = overridden ? edits.cells![k] : r[c.key]
                        return (
                          <td key={c.key} className="border-b border-line p-0.5">
                            <input
                              className={cn('h-6 w-24 rounded-sm bg-transparent px-1 text-[12px] focus:bg-surface', overridden && 'bg-warning-soft')}
                              defaultValue={value === null || value === undefined ? '' : typeof value === 'number' ? Number(value.toFixed(4)) : String(value)}
                              aria-label={`${labelOf(c)}, row ${i + 1}`}
                              onBlur={(e) => {
                                const raw = e.target.value
                                const orig = r[c.key]
                                const parsed: unknown = raw === '' ? null : !Number.isNaN(Number(raw)) && typeof orig === 'number' ? Number(raw) : raw
                                const same = typeof orig === 'number' && typeof parsed === 'number' ? Math.abs(orig - parsed) < 1e-4 : parsed === orig
                                const cells = { ...(edits.cells ?? {}) }
                                if (same) delete cells[k]
                                else cells[k] = parsed
                                onChange({ ...edits, cells })
                              }}
                            />
                          </td>
                        )
                      })}
                    </tr>
                  ))}
                  {(edits.extra_rows ?? []).map((row, ri) => (
                    <tr key={`x${ri}`}>
                      {visibleCols.map((c) => (
                        <td key={c.key} className="border-b border-line p-0.5">
                          <input className="h-6 w-24 rounded-sm bg-warning-soft px-1 text-[12px]" defaultValue={row[c.key] === undefined || row[c.key] === null ? '' : String(row[c.key])} aria-label={`${labelOf(c)}, added row ${ri + 1}`}
                            onBlur={(e) => onChange({ ...edits, extra_rows: (edits.extra_rows ?? []).map((x, j) => (j === ri ? { ...x, [c.key]: e.target.value } : x)) })} />
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            {edits.cells && Object.keys(edits.cells).length > 0 && (
              <Button size="sm" variant="ghost" className="mt-2" onClick={() => onChange({ ...edits, cells: {} })}><RotateCcw /> Restore computed values</Button>
            )}
          </>
        )}
      </section>
      <Field label="Table note">
        {(id) => <Textarea id={id} rows={2} value={edits.notes ?? src.notes.join(' ')} onChange={(e) => onChange({ ...edits, notes: e.target.value })} />}
      </Field>
    </div>
  )
}

function ChartLayout({ block, onChange, onReplace }: { block: ReportBlock; onChange: (e: ChartEdits) => void; onReplace: (chartId: string) => void }) {
  const src = block.source_chart!
  const edits = (block.edits ?? {}) as ChartEdits
  const types = chartTypes(src)
  const styles = chartStyles(resolveChart(src, { type: edits.type }))
  const names = chartNames(src)
  const order = edits.order?.length ? [...edits.order, ...names.groups.filter((n) => !edits.order!.includes(n))] : names.groups
  const hidden = new Set(edits.hidden ?? [])
  const labels = edits.labels ?? {}
  const toggle = (n: string) => {
    const next = new Set(hidden)
    if (next.has(n)) next.delete(n)
    else next.add(n)
    onChange({ ...edits, hidden: [...next] })
  }
  return (
    <div className="space-y-4">
      {(block.alternatives?.length ?? 0) > 1 && (
        <Field label="Chart from this analysis">
          {(id) => (
            <Select id={id} value={block.source?.chart_id} onChange={(e) => onReplace(e.target.value)}>
              {block.alternatives!.map((a) => <option key={a.id} value={a.id}>{a.title}</option>)}
            </Select>
          )}
        </Field>
      )}
      {types.length > 1 && (
        <Field label="Chart type">
          {(id) => (
            <Select id={id} value={edits.type ?? src.type} onChange={(e) => onChange({ ...edits, type: e.target.value })}>
              {types.map((t) => <option key={t} value={t}>{CHART_TYPE_LABEL[t] ?? t}</option>)}
            </Select>
          )}
        </Field>
      )}
      {styles.length > 1 && (
        <fieldset>
          <legend className="mb-1.5 text-[13px] font-medium">Chart style</legend>
          <div className="flex flex-wrap gap-1.5">
            {styles.map((st) => {
              const on = (edits.style ?? defaultStyle(resolveChart(src, { type: edits.type }))) === st
              return (
                <button key={st} type="button" aria-pressed={on} onClick={() => onChange({ ...edits, style: st })}
                  className={cn('rounded-md border px-2.5 py-1 text-[12.5px]', on ? 'border-accent bg-accent-soft font-medium text-fg' : 'border-line text-fg-2 hover:border-fg/30')}>
                  {CHART_STYLE_LABEL[st]}
                </button>
              )
            })}
          </div>
        </fieldset>
      )}
      <div className="grid gap-3 sm:grid-cols-2">
        <Field label="X-axis label">{(id) => <Input id={id} value={edits.x_label ?? src.x_label} onChange={(e) => onChange({ ...edits, x_label: e.target.value })} />}</Field>
        <Field label="Y-axis label">{(id) => <Input id={id} value={edits.y_label ?? src.y_label} onChange={(e) => onChange({ ...edits, y_label: e.target.value })} />}</Field>
      </div>
      <Field label="Caption">{(id) => <Textarea id={id} rows={2} value={edits.caption ?? src.caption} onChange={(e) => onChange({ ...edits, caption: e.target.value })} />}</Field>
      {names.groups.length > 0 && (
        <section>
          <h3 className="label-caps mb-2">Groups and categories</h3>
          <ul className="space-y-1.5">
            {order.map((n, i) => (
              <li key={n} className="flex items-center gap-1.5">
                <button className="rounded p-1 text-muted hover:text-fg" onClick={() => toggle(n)} aria-label={hidden.has(n) ? `Show ${n}` : `Hide ${n}`}>{hidden.has(n) ? <EyeOff className="size-4" /> : <Eye className="size-4" />}</button>
                <Input value={labels[n] ?? n} className={cn('h-7', hidden.has(n) && 'opacity-50')} onChange={(e) => onChange({ ...edits, labels: { ...labels, [n]: e.target.value } })} aria-label={`Label for ${n}`} />
                <button className="rounded p-1 text-muted disabled:opacity-30" disabled={i === 0} onClick={() => onChange({ ...edits, order: move(order, i, -1) })} aria-label="Move up"><ArrowUp className="size-4" /></button>
                <button className="rounded p-1 text-muted disabled:opacity-30" disabled={i === order.length - 1} onClick={() => onChange({ ...edits, order: move(order, i, 1) })} aria-label="Move down"><ArrowDown className="size-4" /></button>
              </li>
            ))}
          </ul>
        </section>
      )}
      {names.series.length > 1 && (
        <section>
          <h3 className="label-caps mb-2">Series (legend)</h3>
          <ul className="space-y-1.5">
            {names.series.map((n) => (
              <li key={n} className="flex items-center gap-1.5">
                <button className="rounded p-1 text-muted hover:text-fg" onClick={() => toggle(n)} aria-label={hidden.has(n) ? `Show ${n}` : `Hide ${n}`}>{hidden.has(n) ? <EyeOff className="size-4" /> : <Eye className="size-4" />}</button>
                <Input value={labels[n] ?? n} className={cn('h-7', hidden.has(n) && 'opacity-50')} onChange={(e) => onChange({ ...edits, labels: { ...labels, [n]: e.target.value } })} aria-label={`Legend name for ${n}`} />
              </li>
            ))}
          </ul>
        </section>
      )}
    </div>
  )
}

export function BlockEditor({
  block,
  dataset,
  spec,
  onUpdate,
  onRebind,
  rebinding,
  onClose,
}: {
  block: ReportBlock
  dataset?: Dataset
  spec?: AnalysisSpec
  onUpdate: (b: ReportBlock) => void
  onRebind: (r: RebindRequest) => void
  rebinding: boolean
  onClose: () => void
}) {
  const [tab, setTab] = useState(block.type === 'table' || block.type === 'chart' ? 'layout' : 'text')
  const kind = { heading: 'Heading', text: 'Text', table: 'Table', chart: 'Chart' }[block.type]
  return (
    <div className="flex h-full flex-col">
      <div className="flex items-center justify-between border-b border-line px-4 py-3">
        <h2 className="text-[15px] font-semibold">Edit {kind.toLowerCase()}</h2>
        <button onClick={onClose} className="rounded p-1 text-muted hover:bg-surface-3 hover:text-fg" aria-label="Close editor"><X className="size-4" /></button>
      </div>
      <div className="scroll-thin min-h-0 flex-1 space-y-4 overflow-y-auto p-4">
        {block.missing && <Callout tone="warning">The analysis behind this item is no longer available. Remove it or replace it with another result.</Callout>}
        {(block.type === 'table' || block.type === 'chart') && (
          <Field label="Title">{(id) => <Input id={id} value={block.title ?? ''} onChange={(e) => onUpdate({ ...block, title: e.target.value, title_edited: true })} />}</Field>
        )}
        {block.type === 'heading' && (
          <Field label="Heading">{(id) => <Input id={id} value={block.text ?? block.resolved_text ?? ''} onChange={(e) => onUpdate({ ...block, text: e.target.value })} />}</Field>
        )}
        {block.type === 'text' && (
          <>
            <Field label="Text">{(id) => <Textarea id={id} rows={10} value={block.text ?? block.resolved_text ?? ''} onChange={(e) => onUpdate({ ...block, text: e.target.value })} />}</Field>
            {block.generated && (
              <div className="flex flex-wrap gap-2">
                <Button size="sm" onClick={() => onUpdate({ ...block, text: block.generated!.plain })}>Use plain version</Button>
                <Button size="sm" onClick={() => onUpdate({ ...block, text: block.generated!.technical })}>Use technical version</Button>
                {block.text !== null && block.text !== undefined && <Button size="sm" variant="ghost" onClick={() => onUpdate({ ...block, text: null })}><RotateCcw /> Generated text</Button>}
              </div>
            )}
          </>
        )}
        {(block.type === 'table' || block.type === 'chart') && !block.missing && (
          <Tabs value={tab} onValueChange={setTab}>
            <TabsList>
              <TabsTrigger value="layout">Layout</TabsTrigger>
              {block.analysis && dataset && <TabsTrigger value="data">Data</TabsTrigger>}
            </TabsList>
            <TabsContent value="layout" className="pt-4">
              {block.type === 'table' && block.source_table && <TableLayout block={block} onChange={(edits) => onUpdate({ ...block, edits: edits as Record<string, unknown> })} />}
              {block.type === 'chart' && block.source_chart && <ChartLayout block={block} onChange={(edits) => onUpdate({ ...block, edits: edits as Record<string, unknown> })} onReplace={(chart_id) => onRebind({ chart_id })} />}
            </TabsContent>
            {block.analysis && dataset && (
              <TabsContent value="data" className="pt-4">
                <ScopeEditor key={block.source?.run_id} block={block} dataset={dataset} spec={spec} onRebind={onRebind} busy={rebinding} />
              </TabsContent>
            )}
          </Tabs>
        )}
      </div>
    </div>
  )
}
