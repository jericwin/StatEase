import { BarChart, BoxplotChart, CustomChart, HeatmapChart, LineChart, ScatterChart } from 'echarts/charts'
import { GridComponent, LegendComponent, MarkLineComponent, TooltipComponent, VisualMapComponent } from 'echarts/components'
import * as echarts from 'echarts/core'
import { SVGRenderer } from 'echarts/renderers'
import { ChartBar, ChartBarStacked, ChartColumn, ChartLine, ChartPie, ChartScatter, ChevronDown, Table2 } from 'lucide-react'
import { useEffect, useMemo, useRef, useState } from 'react'
import { ErrorBoundary } from '@/components/RouteError'
import { CHART_STYLE_LABEL, chartStyles, defaultStyle, withStyle } from '@/lib/blocks'
import type { ChartSpec, ChartStyle } from '@/lib/types'

echarts.use([BarChart, BoxplotChart, CustomChart, HeatmapChart, LineChart, ScatterChart, GridComponent, LegendComponent, MarkLineComponent, TooltipComponent, VisualMapComponent, SVGRenderer])

type Num = number | null
type D = Record<string, unknown>

/** Minimal ECharts host: one instance per element, resized with the container, disposed on unmount. */
function EChart({ option, height }: { option: echarts.EChartsCoreOption; height: number }) {
  const el = useRef<HTMLDivElement>(null)
  const chart = useRef<echarts.ECharts | null>(null)
  useEffect(() => {
    if (!el.current) return
    const instance = echarts.init(el.current, undefined, { renderer: 'svg' })
    chart.current = instance
    const ro = new ResizeObserver(() => instance.resize())
    ro.observe(el.current)
    return () => {
      ro.disconnect()
      instance.dispose()
      chart.current = null
    }
  }, [])
  useEffect(() => {
    chart.current?.setOption(option, { notMerge: true })
  }, [option])
  return <div ref={el} style={{ height, width: '100%' }} />
}

const LIGHT: Record<string, string> = {
  '--text-2': '#3d4655', '--muted': '#667085', '--border': '#e1e4e9', '--surface': '#ffffff', '--accent-soft': '#eaf1fa',
  '--chart-1': '#1d4f91', '--chart-2': '#b5523b', '--chart-3': '#3f7d5a', '--chart-4': '#b88a1c', '--chart-5': '#6a5a95', '--chart-6': '#3c8aa8',
}
let paperMode = false

function cssVar(name: string) {
  if (paperMode && LIGHT[name]) return LIGHT[name]
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim()
}

function useThemeKey() {
  const [k, setK] = useState(0)
  useEffect(() => {
    const h = () => setK((x) => x + 1)
    window.addEventListener('statease:theme', h)
    const mq = window.matchMedia('(prefers-color-scheme: dark)')
    mq.addEventListener('change', h)
    return () => {
      window.removeEventListener('statease:theme', h)
      mq.removeEventListener('change', h)
    }
  }, [])
  return k
}

/** Pixel gap between dots of different series in the same category (dot plots). */
const DOT_STEP = 12

const fmt = (v: number) => (Math.abs(v) >= 1000 ? v.toLocaleString('en-US', { maximumFractionDigits: 0 }) : Number(v.toFixed(3)).toString())

function buildOption(spec: ChartSpec) {
  const text = cssVar('--text-2')
  const muted = cssVar('--muted')
  const line = cssVar('--border')
  const palette = [1, 2, 3, 4, 5, 6].map((i) => cssVar(`--chart-${i}`))
  const accent = palette[0]
  const d = spec.data as D
  const axis = (name: string, extra: object = {}) => ({
    name,
    nameLocation: 'middle' as const,
    nameGap: 30,
    nameTextStyle: { color: text, fontSize: 12 },
    axisLine: { lineStyle: { color: muted } },
    axisLabel: { color: muted, fontSize: 11, hideOverlap: true },
    splitLine: { lineStyle: { color: line } },
    ...extra,
  })
  const base = {
    color: palette,
    textStyle: { fontFamily: 'IBM Plex Sans, sans-serif' },
    grid: { left: 56, right: 20, top: 24, bottom: 52, containLabel: false },
    tooltip: { trigger: 'item' as const, backgroundColor: cssVar('--surface'), borderColor: line, textStyle: { color: text, fontSize: 12 } },
    animation: false,
  }
  if (spec.style && ['means', 'bar', 'interaction'].includes(spec.type)) {
    const style = spec.style
    const cats = (d.categories as string[]) ?? []
    const series = (d.series as { name: string; values: Num[]; lower?: Num[]; upper?: Num[] }[]) ?? []
    const legend = series.length > 1 ? { top: 0, textStyle: { color: text, fontSize: 11 }, type: 'scroll' as const } : undefined
    if (style === 'pie') {
      const s = series[0]
      return {
        ...base,
        legend: { bottom: 0, textStyle: { color: text, fontSize: 11 }, type: 'scroll' as const },
        series: [{
          type: 'pie',
          radius: ['0%', '62%'],
          center: ['50%', '45%'],
          data: cats.map((c, i) => ({ name: c, value: s?.values[i] ?? 0 })).filter((x) => (x.value ?? 0) > 0),
          label: { color: text, fontSize: 11, formatter: '{b}\n{d}%' },
          itemStyle: { borderColor: cssVar('--surface'), borderWidth: 1 },
        }],
        tooltip: { ...base.tooltip, formatter: (p: { name: string; value: number; percent: number }) => `${p.name}: ${fmt(p.value)} (${p.percent}%)` },
      }
    }
    const horizontal = style === 'hbar'
    const long = cats.some((c) => c.length > 10)
    const n = Math.max(series.length, 1)
    const catAxis = axis(horizontal ? '' : spec.x_label, {
      type: 'category', data: cats, splitLine: { show: false }, inverse: horizontal,
      axisLabel: { color: muted, fontSize: 11, interval: 0, rotate: !horizontal && long ? 25 : 0 },
      nameGap: long ? 60 : 30,
    })
    const valAxis = axis(spec.y_label, { type: 'value', max: d.percent ? 100 : undefined, scale: style === 'line' || style === 'dot', nameGap: horizontal ? 30 : 44 })
    const out: object[] = []
    series.forEach((s, si) => {
      const color = palette[si % palette.length]
      if (style === 'line') out.push({ type: 'line', name: s.name, data: s.values, symbolSize: 7, itemStyle: { color }, lineStyle: { width: 2 } })
      else if (style === 'dot') out.push({ type: 'scatter', name: s.name, data: s.values, symbolSize: 10, symbolOffset: [(si - (n - 1) / 2) * DOT_STEP, 0], itemStyle: { color } })
      else out.push({ type: 'bar', name: s.name, data: s.values, stack: style === 'stacked' ? 'total' : undefined, barMaxWidth: 44, itemStyle: { color } })
      if (style === 'stacked' || !s.lower || !s.upper) return
      // Error bars follow the style: offset like grouped bars, small offset for dots, centred for lines.
      out.push({
        type: 'custom',
        name: `${s.name} CI`,
        tooltip: { show: false },
        encode: horizontal ? { x: [1, 2], y: 0 } : { x: 0, y: [1, 2] },
        renderItem: (params: { coordSys: { width: number; height: number } }, api: { value: (i: number) => number; coord: (v: number[]) => number[] }) => {
          const band = (horizontal ? params.coordSys.height : params.coordSys.width) / Math.max(cats.length, 1)
          const step = style === 'line' ? 0 : style === 'dot' ? DOT_STEP : Math.min(44, (band * 0.8) / n)
          const offset = (si - (n - 1) / 2) * step
          const at = (v: number) => (horizontal ? api.coord([v, api.value(0)]) : api.coord([api.value(0), v]))
          const lo = at(api.value(1))
          const hi = at(api.value(2))
          const stroke = style === 'bar' || style === 'hbar' ? text : color
          return horizontal
            ? { type: 'group', children: [
                { type: 'line', shape: { x1: lo[0], y1: lo[1] + offset, x2: hi[0], y2: hi[1] + offset }, style: { stroke, lineWidth: 1 } },
                { type: 'line', shape: { x1: lo[0], y1: lo[1] + offset - 4, x2: lo[0], y2: lo[1] + offset + 4 }, style: { stroke, lineWidth: 1 } },
                { type: 'line', shape: { x1: hi[0], y1: hi[1] + offset - 4, x2: hi[0], y2: hi[1] + offset + 4 }, style: { stroke, lineWidth: 1 } },
              ] }
            : { type: 'group', children: [
                { type: 'line', shape: { x1: lo[0] + offset, y1: lo[1], x2: hi[0] + offset, y2: hi[1] }, style: { stroke, lineWidth: 1 } },
                { type: 'line', shape: { x1: lo[0] + offset - 4, y1: lo[1], x2: lo[0] + offset + 4, y2: lo[1] }, style: { stroke, lineWidth: 1 } },
                { type: 'line', shape: { x1: hi[0] + offset - 4, y1: hi[1], x2: hi[0] + offset + 4, y2: hi[1] }, style: { stroke, lineWidth: 1 } },
              ] }
        },
        data: cats.map((_, i) => [i, s.lower![i], s.upper![i]]).filter((v) => v[1] !== null && v[2] !== null),
        z: 3,
      })
    })
    return {
      ...base,
      legend: legend && { ...legend, data: series.map((s) => s.name) },
      grid: horizontal
        ? { left: 16, right: 24, top: series.length > 1 ? 36 : 16, bottom: 48, containLabel: true }
        : { ...base.grid, left: 64, top: series.length > 1 ? 36 : 24, bottom: long ? 80 : 52 },
      xAxis: horizontal ? valAxis : catAxis,
      yAxis: horizontal ? catAxis : valAxis,
      tooltip: { ...base.tooltip, trigger: 'axis' as const, axisPointer: { type: 'shadow' as const } },
      series: out,
    }
  }
  switch (spec.type) {
    case 'histogram': {
      const bins = (d.bins as [number, number, number][]) ?? []
      const normal = (d.normal as [number, number][]) ?? []
      return {
        ...base,
        xAxis: axis(spec.x_label, { type: 'value', scale: true, splitLine: { show: false } }),
        yAxis: axis(spec.y_label, { type: 'value' }),
        series: [
          {
            type: 'custom',
            name: 'Frequency',
            renderItem: (_p: unknown, api: { value: (i: number) => number; coord: (v: number[]) => number[]; size: (v: number[]) => number[] }) => {
              const start = api.coord([api.value(0), api.value(2)])
              const size = api.size([api.value(1) - api.value(0), api.value(2)])
              return { type: 'rect', shape: { x: start[0], y: start[1], width: Math.max(size[0] - 1, 1), height: size[1] }, style: { fill: accent, opacity: 0.85 } }
            },
            encode: { x: [0, 1], y: 2 },
            data: bins,
            tooltip: { formatter: (p: { value: number[] }) => `${fmt(p.value[0])} – ${fmt(p.value[1])}: ${p.value[2]}` },
          },
          ...(normal.length ? [{ type: 'line', name: 'Normal curve', data: normal, showSymbol: false, smooth: true, lineStyle: { color: palette[1], width: 1.5 }, tooltip: { show: false } }] : []),
        ],
      }
    }
    case 'box': {
      const groups = ((d.groups as D[]) ?? []).filter((g) => g.n)
      const outliers = groups.flatMap((g, i) => ((g.outliers as number[]) ?? []).map((v) => [i, v]))
      return {
        ...base,
        xAxis: axis(spec.x_label, { type: 'category', data: groups.map((g) => g.name), splitLine: { show: false } }),
        yAxis: axis(spec.y_label, { type: 'value', scale: true, nameGap: 44 }),
        grid: { ...base.grid, left: 64 },
        series: [
          {
            type: 'boxplot',
            data: groups.map((g) => [g.min, g.q1, g.median, g.q3, g.max]),
            itemStyle: { color: cssVar('--accent-soft'), borderColor: accent },
            tooltip: { formatter: (p: { dataIndex: number }) => { const g = groups[p.dataIndex]; return `${g.name} (n = ${g.n})<br/>Median ${fmt(g.median as number)}<br/>Q1–Q3 ${fmt(g.q1 as number)} – ${fmt(g.q3 as number)}` } },
          },
          { type: 'scatter', data: outliers, symbolSize: 5, itemStyle: { color: muted }, name: 'Outliers' },
        ],
      }
    }
    case 'meanci': {
      const groups = ((d.groups as D[]) ?? []).filter((g) => g.mean !== undefined && g.mean !== null)
      return {
        ...base,
        xAxis: axis(spec.x_label, { type: 'category', data: groups.map((g) => g.name), splitLine: { show: false } }),
        yAxis: axis(spec.y_label, { type: 'value', scale: true, nameGap: 44 }),
        grid: { ...base.grid, left: 64 },
        series: [
          {
            type: 'custom',
            name: 'CI',
            renderItem: (_p: unknown, api: { value: (i: number) => number; coord: (v: number[]) => number[] }) => {
              const lo = api.coord([api.value(0), api.value(1)])
              const hi = api.coord([api.value(0), api.value(2)])
              const w = 7
              return {
                type: 'group',
                children: [
                  { type: 'line', shape: { x1: lo[0], y1: lo[1], x2: hi[0], y2: hi[1] }, style: { stroke: accent, lineWidth: 1.5 } },
                  { type: 'line', shape: { x1: lo[0] - w, y1: lo[1], x2: lo[0] + w, y2: lo[1] }, style: { stroke: accent, lineWidth: 1.5 } },
                  { type: 'line', shape: { x1: hi[0] - w, y1: hi[1], x2: hi[0] + w, y2: hi[1] }, style: { stroke: accent, lineWidth: 1.5 } },
                ],
              }
            },
            data: groups.map((g, i) => [i, g.lower ?? g.mean, g.upper ?? g.mean]),
            tooltip: { show: false },
            z: 1,
          },
          {
            type: 'scatter',
            name: 'Mean',
            data: groups.map((g, i) => [i, g.mean]),
            symbolSize: 9,
            itemStyle: { color: accent },
            z: 2,
            tooltip: { formatter: (p: { dataIndex: number }) => { const g = groups[p.dataIndex]; return `${g.name}: M = ${fmt(g.mean as number)}${g.lower !== null && g.lower !== undefined ? `<br/>CI [${fmt(g.lower as number)}, ${fmt(g.upper as number)}]` : ''}` } },
          },
        ],
      }
    }
    case 'qq':
    case 'scatter': {
      const pts = (d.points as [number, number][]) ?? []
      const series: object[] = [{ type: 'scatter', data: pts, symbolSize: pts.length > 800 ? 3 : 5, itemStyle: { color: accent, opacity: 0.6 }, name: 'Observations' }]
      const lineDef = (spec.type === 'qq' ? d.line : d.fit) as D | undefined
      if (lineDef && pts.length) {
        const xs = pts.map((p) => p[0])
        const x0 = spec.type === 'qq' ? Math.min(...xs) : (lineDef.x_min as number)
        const x1 = spec.type === 'qq' ? Math.max(...xs) : (lineDef.x_max as number)
        const y = (x: number) => (lineDef.intercept as number) + (lineDef.slope as number) * x
        series.push({ type: 'line', data: [[x0, y(x0)], [x1, y(x1)]], showSymbol: false, lineStyle: { color: palette[1], width: 1.5 }, tooltip: { show: false }, name: spec.type === 'qq' ? 'Reference line' : 'Fitted line' })
      }
      if (d.zero_line) series.push({ type: 'line', markLine: { silent: true, symbol: 'none', lineStyle: { color: palette[1], type: 'dashed' }, data: [{ yAxis: 0 }] }, data: [] })
      return {
        ...base,
        xAxis: axis(spec.x_label, { type: 'value', scale: true }),
        yAxis: axis(spec.y_label, { type: 'value', scale: true, nameGap: 44 }),
        grid: { ...base.grid, left: 64 },
        tooltip: { ...base.tooltip, formatter: (p: { value: number[] }) => `${fmt(p.value[0])}, ${fmt(p.value[1])}` },
        series,
      }
    }
    case 'bar': {
      const cats = (d.categories as string[]) ?? []
      const series = (d.series as { name: string; values: Num[] }[]) ?? []
      const stacked = Boolean(d.stacked)
      return {
        ...base,
        legend: series.length > 1 ? { top: 0, textStyle: { color: text, fontSize: 11 }, type: 'scroll' as const } : undefined,
        grid: { ...base.grid, top: series.length > 1 ? 36 : 24, bottom: cats.some((c) => c.length > 10) ? 80 : 52 },
        xAxis: axis(spec.x_label, { type: 'category', data: cats, splitLine: { show: false }, axisLabel: { color: muted, fontSize: 11, interval: 0, rotate: cats.some((c) => c.length > 10) ? 30 : 0 }, nameGap: cats.some((c) => c.length > 10) ? 60 : 30 }),
        yAxis: axis(spec.y_label, { type: 'value', max: d.percent ? 100 : undefined }),
        tooltip: { ...base.tooltip, trigger: 'axis' as const },
        series: series.map((s) => ({ type: 'bar', name: s.name, data: s.values, stack: stacked ? 'total' : undefined, barMaxWidth: 48 })),
      }
    }
    case 'means': {
      const cats = (d.categories as string[]) ?? []
      const series = (d.series as { name: string; values: Num[]; lower?: Num[]; upper?: Num[] }[]) ?? []
      const n = Math.max(series.length, 1)
      const out: object[] = []
      series.forEach((s, si) => {
        out.push({ type: 'bar', name: s.name, data: s.values, barMaxWidth: 44, itemStyle: { color: palette[si % palette.length] } })
        if (s.lower && s.upper)
          out.push({
            type: 'custom',
            name: `${s.name} CI`,
            tooltip: { show: false },
            renderItem: (params: { coordSys: { width: number } }, api: { value: (i: number) => number; coord: (v: number[]) => number[] }) => {
              const bandWidth = params.coordSys.width / Math.max(cats.length, 1)
              const offset = (si - (n - 1) / 2) * Math.min(44, (bandWidth * 0.8) / n)
              const lo = api.coord([api.value(0), api.value(1)])
              const hi = api.coord([api.value(0), api.value(2)])
              const x = lo[0] + offset
              return { type: 'group', children: [
                { type: 'line', shape: { x1: x, y1: lo[1], x2: x, y2: hi[1] }, style: { stroke: text, lineWidth: 1 } },
                { type: 'line', shape: { x1: x - 4, y1: lo[1], x2: x + 4, y2: lo[1] }, style: { stroke: text, lineWidth: 1 } },
                { type: 'line', shape: { x1: x - 4, y1: hi[1], x2: x + 4, y2: hi[1] }, style: { stroke: text, lineWidth: 1 } },
              ] }
            },
            data: cats.map((_, i) => [i, s.lower![i], s.upper![i]]).filter((v) => v[1] !== null && v[2] !== null),
            z: 3,
          })
      })
      return {
        ...base,
        legend: series.length > 1 ? { top: 0, textStyle: { color: text, fontSize: 11 }, data: series.map((s) => s.name) } : undefined,
        grid: { ...base.grid, top: series.length > 1 ? 36 : 24, bottom: cats.some((c) => c.length > 10) ? 80 : 52 },
        xAxis: axis(spec.x_label, { type: 'category', data: cats, splitLine: { show: false }, axisLabel: { color: muted, fontSize: 11, interval: 0, rotate: cats.some((c) => c.length > 10) ? 25 : 0 }, nameGap: cats.some((c) => c.length > 10) ? 60 : 30 }),
        yAxis: axis(spec.y_label, { type: 'value' }),
        tooltip: { ...base.tooltip, trigger: 'axis' as const },
        series: out,
      }
    }
    case 'heatmap': {
      const labels = (d.labels as string[]) ?? []
      const m = (d.matrix as Num[][]) ?? []
      const data = m.flatMap((row, i) => row.map((v, j) => [j, i, v === null ? '-' : Number(v.toFixed(2))]))
      return {
        ...base,
        grid: { left: 110, right: 20, top: 10, bottom: 90 },
        xAxis: { type: 'category', data: labels, axisLabel: { color: muted, fontSize: 11, rotate: 40, interval: 0 }, splitArea: { show: false } },
        yAxis: { type: 'category', data: labels, axisLabel: { color: muted, fontSize: 11, interval: 0 }, inverse: true },
        visualMap: { min: -1, max: 1, show: false, inRange: { color: ['#b5523b', '#f3f4f6', '#1d4f91'] } },
        series: [{ type: 'heatmap', data, label: { show: labels.length <= 10, fontSize: 10, color: '#111' }, itemStyle: { borderColor: cssVar('--surface'), borderWidth: 1 } }],
        tooltip: { ...base.tooltip, formatter: (p: { value: [number, number, number] }) => `${labels[p.value[1]]} × ${labels[p.value[0]]}: ${p.value[2]}` },
      }
    }
    case 'interaction': {
      const cats = (d.categories as string[]) ?? []
      const series = (d.series as { name: string; values: Num[] }[]) ?? []
      return {
        ...base,
        legend: { top: 0, textStyle: { color: text, fontSize: 11 }, type: 'scroll' as const },
        grid: { ...base.grid, top: 36, left: 64 },
        xAxis: axis(spec.x_label, { type: 'category', data: cats, splitLine: { show: false } }),
        yAxis: axis(spec.y_label, { type: 'value', scale: true, nameGap: 44 }),
        tooltip: { ...base.tooltip, trigger: 'axis' as const },
        series: series.map((s) => ({ type: 'line', name: s.name, data: s.values, symbolSize: 7 })),
      }
    }
  }
}

function dataTable(spec: ChartSpec): { columns: string[]; rows: (string | number)[][] } {
  const d = spec.data as D
  const r = (v: unknown) => (typeof v === 'number' ? Number(v.toFixed(4)) : String(v ?? ''))
  switch (spec.type) {
    case 'histogram':
      return { columns: ['From', 'To', 'Count'], rows: ((d.bins as number[][]) ?? []).map((b) => b.map(r)) }
    case 'box':
      return { columns: ['Group', 'N', 'Min', 'Q1', 'Median', 'Q3', 'Max', 'Outliers'], rows: ((d.groups as D[]) ?? []).map((g) => [g.name, g.n, g.min, g.q1, g.median, g.q3, g.max, g.n_outliers].map(r)) }
    case 'meanci':
      return { columns: ['Group', 'N', 'Mean', 'CI lower', 'CI upper'], rows: ((d.groups as D[]) ?? []).map((g) => [g.name, g.n, g.mean, g.lower, g.upper].map(r)) }
    case 'means': {
      const series = (d.series as { name: string; values: Num[]; lower?: Num[]; upper?: Num[] }[]) ?? []
      return { columns: ['Category', ...series.flatMap((s) => [s.name, `${s.name} CI lower`, `${s.name} CI upper`])], rows: ((d.categories as string[]) ?? []).map((c, i) => [c, ...series.flatMap((s) => [r(s.values[i]), r(s.lower?.[i]), r(s.upper?.[i])])]) }
    }
    case 'bar':
    case 'interaction': {
      const series = (d.series as { name: string; values: Num[] }[]) ?? []
      return { columns: ['Category', ...series.map((s) => s.name)], rows: ((d.categories as string[]) ?? []).map((c, i) => [c, ...series.map((s) => r(s.values[i]))]) }
    }
    case 'heatmap': {
      const labels = (d.labels as string[]) ?? []
      return { columns: ['', ...labels], rows: ((d.matrix as Num[][]) ?? []).map((row, i) => [labels[i], ...row.map(r)]) }
    }
    default:
      return { columns: [spec.x_label || 'x', spec.y_label || 'y'], rows: ((d.points as number[][]) ?? []).slice(0, 200).map((p) => p.map(r)) }
  }
}

/**
 * A figure with its caption, a style switcher (bar, horizontal bar, line, dot plot, stacked, pie — whichever suit the data)
 * and a data-table toggle. Pass onStyleChange to store the choice (the report does); otherwise it is a view setting.
 */
export function ChartView({ spec: source, number, paper, onStyleChange }: { spec: ChartSpec; number?: number; paper?: boolean; onStyleChange?: (style: ChartStyle) => void }) {
  const themeKey = useThemeKey()
  const styles = chartStyles(source)
  const [picked, setPicked] = useState<ChartStyle | undefined>()
  const spec = useMemo(() => (picked && !onStyleChange ? withStyle(source, picked) : source), [source, picked, onStyleChange])
  const current = defaultStyle(spec)
  const option = useMemo(() => {
    paperMode = !!paper
    try {
      return buildOption(spec)
    } finally {
      paperMode = false
    }
  }, [spec, themeKey, paper]) // eslint-disable-line react-hooks/exhaustive-deps
  const [asTable, setAsTable] = useState(false)
  const nCats = ((spec.data.categories as string[]) ?? []).length
  const nSeries = Math.max(((spec.data.series as unknown[]) ?? []).length, 1)
  const height =
    spec.type === 'heatmap' ? Math.max(300, 40 + ((spec.data.labels as string[])?.length ?? 4) * 34)
    : spec.style === 'hbar' ? Math.max(260, 70 + nCats * Math.max(30, nSeries * 16))
    : 300
  const table = asTable ? dataTable(spec) : null
  return (
    <figure className="min-w-0 rounded-md border border-line bg-surface p-3">
      <figcaption className="mb-1 flex items-start justify-between gap-2 text-[13px]">
        <span>
          {number !== undefined && <span className="font-semibold">Figure {number}. </span>}
          <span className="italic">{spec.title}</span>
        </span>
        <span className="flex shrink-0 items-center gap-1">
          {styles.length > 1 && !asTable && (
            <label className="relative flex items-center rounded text-xs text-muted hover:bg-surface-3 hover:text-fg">
              <span className="sr-only">Chart style</span>
              <ChartIcon style={current} />
              <select
                value={current}
                onChange={(e) => {
                  const v = e.target.value as ChartStyle
                  if (onStyleChange) onStyleChange(v)
                  else setPicked(v)
                }}
                className="cursor-pointer appearance-none bg-transparent py-0.5 pr-5 pl-6 text-xs focus:outline-none"
              >
                {styles.map((st) => <option key={st} value={st}>{CHART_STYLE_LABEL[st]}</option>)}
              </select>
              <ChevronDown className="pointer-events-none absolute right-1 size-3" />
            </label>
          )}
          <button
            type="button"
            onClick={() => setAsTable(!asTable)}
            className="flex items-center gap-1 rounded px-1.5 py-0.5 text-xs text-muted hover:bg-surface-3 hover:text-fg"
            aria-pressed={asTable}
          >
            <Table2 className="size-3.5" /> {asTable ? 'Chart' : 'Data'}
          </button>
        </span>
      </figcaption>
      {table ? (
        <div className="scroll-thin max-h-[300px] overflow-auto [contain:paint]">
          <table className="stat-table">
            <thead>
              <tr>{table.columns.map((c) => <th key={c}>{c}</th>)}</tr>
            </thead>
            <tbody>
              {table.rows.map((row, i) => (
                <tr key={i}>{row.map((v, j) => <td key={j} className={typeof v === 'number' ? 'num text-right' : ''}>{v}</td>)}</tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <div role="img" aria-label={`${spec.title}. ${spec.caption}`}>
          <ErrorBoundary label="figure" resetKey={option}>
            <EChart option={(option ?? {}) as echarts.EChartsCoreOption} height={height} />
          </ErrorBoundary>
        </div>
      )}
      {(spec.caption || spec.note) && <p className="mt-1 text-xs text-muted">{[spec.caption, spec.note].filter(Boolean).join(' ')}</p>}
    </figure>
  )
}

function ChartIcon({ style }: { style?: ChartStyle }) {
  const Icon = { bar: ChartColumn, hbar: ChartBar, line: ChartLine, dot: ChartScatter, stacked: ChartBarStacked, pie: ChartPie }[style ?? 'bar']
  return <Icon className="pointer-events-none absolute left-1 size-3.5" aria-hidden />
}
