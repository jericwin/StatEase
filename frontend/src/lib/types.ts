export type Level = 'numeric' | 'ordinal' | 'nominal' | 'binary' | 'date' | 'datetime' | 'text' | 'identifier'

export interface Paged<T> {
  items: T[]
  total: number
  limit?: number
  offset?: number
}

export interface ProjectSettings {
  alpha: number
  ci_level: number
  p_style: 'apa' | 'academic'
  decimals: number
}

export interface Project {
  id: number
  name: string
  description: string | null
  status: 'active' | 'archived'
  is_demo: boolean
  settings: ProjectSettings
  created_at: string
  updated_at: string
  counts: { datasets: number; analyses: number; results: number }
}

export interface VariableProfile {
  name: string
  missing: number
  unique: number
  missing_pct: number
  mean?: number | null
  sd?: number | null
  min?: number | string | null
  max?: number | string | null
  median?: number | null
  categories?: { value: string | number; count: number }[]
}

export interface Variable {
  id: number
  name: string
  label: string | null
  level: Level
  data_type: string
  inferred_level: Level | null
  inference_note: string | null
  category_labels: Record<string, string>
  category_order: (string | number)[]
  missing_codes: (string | number)[]
  unit: string | null
  scale_group: string | null
  profile: Partial<VariableProfile>
}

export interface DataWarning {
  code: string
  column?: string
  message: string
}

export interface DatasetSummary {
  id: number
  project_id: number
  name: string
  source_filename: string | null
  format: string
  row_count: number
  column_count: number
  created_at: string
  lineage: Record<string, unknown> & {
    sql?: string
    synthetic?: boolean
    transforms?: { version: number; note: string }[]
    cleaning?: { version: number; from_version: number; log: string[]; rows_before: number; rows_after: number }[]
  }
  parent_version_id: number | null
  version: { id: number; number: number; note: string | null; sha256: string; created_at: string }
  versions: { id: number; number: number; note: string | null; rows: number; created_at: string }[]
}

export type CleaningOp =
  | 'trim_text' | 'change_case' | 'recode' | 'to_number' | 'missing_codes' | 'drop_duplicates' | 'drop_missing'
  | 'fill_missing' | 'out_of_range' | 'outliers' | 'rename' | 'drop_columns'

export interface CleaningStep {
  op: CleaningOp
  column?: string
  columns?: string[]
  mapping?: Record<string, string>
  codes?: string[]
  case?: 'title' | 'lower' | 'upper' | 'sentence'
  how?: 'any' | 'all'
  method?: string
  value?: string
  min?: number | null
  max?: number | null
  action?: 'missing' | 'drop'
  to?: string
}

export interface CleaningSummary {
  rows: number
  columns: number
  missing_cells: number
  duplicate_rows: number
  empty_rows: number
}

export interface CleaningSuggestion {
  id: string
  kind: string
  title: string
  detail: string
  step: CleaningStep
  default: boolean
  examples: string[]
}

export interface CleaningPreview {
  before: CleaningSummary
  after: CleaningSummary
  log: { step: number; op: CleaningOp; message: string; rows_before: number; rows_after: number }[]
  columns: string[]
  rows: unknown[][]
  changed: [number, string][]
}

export interface Dataset extends DatasetSummary {
  variables: Variable[]
  profile: { rows: number; columns: number; total_missing: number; duplicate_rows: number; complete_rows: number; warnings: DataWarning[] }
}

export interface ImportIssue {
  code: string
  column?: string
  message: string
  severity?: 'error' | 'warning'
  suggested_format?: string | null
  values?: string[]
}

export interface InferredVariable {
  column_name: string
  measurement_level: Level
  inferred_level: Level
  data_type: string
  inference_note: string
  n_missing: number
  n_unique: number
  examples: string[]
  category_order: (string | number)[]
  scale_group?: string
  constant?: boolean
}

export interface ImportPreview {
  upload: { upload_id: string; filename: string; format: string; size_bytes: number }
  detected: { delimiter?: string; sheets?: string[]; sheet?: string }
  issues: ImportIssue[]
  columns: string[]
  rows: unknown[][]
  sample_rows?: number
  variables: InferredVariable[]
}

export interface Role {
  key: string
  label: string
  description: string
  levels: Level[]
  min: number
  max: number | null
  plain: string
}

export interface OptionSpec {
  key: string
  label: string
  type: 'bool' | 'number' | 'select' | 'multiselect' | 'text' | 'level' | 'levels'
  default: unknown
  choices: { value: string; label: string }[] | null
  help: string
  advanced: boolean
  depends_on: string | null
  min: number | null
  max: number | null
}

export interface AnalysisSpec {
  id: string
  name: string
  plain_name: string
  category: string
  description: string
  when_to_use: string
  roles: Role[]
  options: OptionSpec[]
  assumptions: string[]
  method: string
  missing_data: string
  references: string[]
  limitations: string[]
}

export interface Catalog {
  categories: { id: string; name: string; plain: string }[]
  analyses: AnalysisSpec[]
}

export type Assignment = Record<string, string | string[]>

export interface Run {
  id: number
  configuration_id: number
  status: 'queued' | 'running' | 'completed' | 'failed' | 'cancelled'
  error_code: string | null
  error_message: string | null
  summary: Record<string, unknown> & { suggestion?: string | null; problems?: string[] | null; title?: string; p?: number; significant?: boolean }
  duration_ms: number | null
  dataset_version_id: number
  created_at: string
  completed_at: string | null
}

export interface Configuration {
  id: number
  project_id: number
  dataset_version_id: number
  dataset_id: number
  dataset_version_number: number
  outdated: boolean
  analysis_type: string
  analysis_name: string
  plain_name: string
  category: string | null
  name: string | null
  variables: Assignment
  options: Record<string, unknown>
  source: 'manual' | 'recommended'
  position: number
  problems: string[]
  created_at: string
  updated_at: string
  last_run: Run | null
}

export interface Recommendation {
  key: string
  kind: 'analysis' | 'transform'
  analysis_type: string
  technical_name: string
  config: { variables: Assignment; options: Record<string, unknown> }
  title: string
  question: string
  test: string
  why: string
  limitations: string[]
  alternative: string | null
  score: number
  added: boolean
}

export interface Recommendations {
  recommendations: Recommendation[]
  excluded: { name: string; reason: string }[]
  summary: { numeric: number; ordinal: number; grouping: number; scales: number; rows: number }
  dataset_version_id: number
  profile_warnings: DataWarning[]
}

export type ColumnFmt = 'int' | 'num' | 'stat' | 'p' | 'pct' | 'ci' | 'text' | 'r'

export interface ResultColumn {
  key: string
  label: string
  fmt: ColumnFmt
  group?: string
  help?: string
}

export type ResultRow = Record<string, unknown> & { _style?: 'total' | 'muted' }

export interface ResultTable {
  id: string
  kind: 'descriptives' | 'frequencies' | 'main' | 'posthoc' | 'effect' | 'assumptions'
  title: string
  columns: ResultColumn[]
  rows: ResultRow[]
  notes: string[]
}

export type ChartStyle = 'bar' | 'hbar' | 'line' | 'dot' | 'stacked' | 'pie'

export interface ChartSpec {
  id: string
  type: 'histogram' | 'box' | 'meanci' | 'means' | 'qq' | 'scatter' | 'bar' | 'heatmap' | 'interaction'
  /** Drawing style for category charts; absent means the type's natural style. */
  style?: ChartStyle
  title: string
  data: Record<string, unknown>
  x_label: string
  y_label: string
  caption: string
  note: string | null
}

export interface Assumption {
  name: string
  status: 'ok' | 'warning' | 'violated' | 'info'
  message: string
  statistic?: number
  p?: number
  test?: string
}

export interface AnalysisResult {
  analysis_type: string
  title: string
  plain_title: string
  heading?: string
  category: string
  variables: Assignment
  options: Record<string, unknown>
  n: number | null
  missing: { total_rows?: number; used?: number; excluded?: number; method?: string }
  tables: ResultTable[]
  charts: ChartSpec[]
  assumptions: Assumption[]
  warnings: string[]
  notes: string[]
  summary: { statistic?: number; p?: number; effect?: number; effect_name?: string; significant?: boolean | null; df?: unknown }
  interpretation: { plain: string; technical: string }
  settings: { alpha: number; ci_level: number }
  method: { description: string; assumptions: string[]; missing_data: string; references: string[]; limitations: string[] }
  code: string | null
  dataset_version_id: number
}

export interface ResultItem {
  configuration: { id: number; name: string | null; analysis_type: string }
  run: Run
  result: AnalysisResult | null
  edited_interpretation: string | null
}

export interface ExportRecord {
  id: number
  project_id: number
  format: 'docx' | 'xlsx'
  status: 'pending' | 'completed' | 'failed'
  filename: string | null
  size_bytes: number | null
  error: string | null
  summary: { tables: number; figures: number; figures_failed: number; sheets?: string[] } | null
  created_at: string
  download_url: string | null
}

export interface ReportOptions {
  title: string
  subtitle: string | null
  author: string | null
  style: 'apa' | 'academic'
  decimals: number
  run_ids: number[]
  sections: Record<string, boolean>
  descriptive_stats: string[] | null
  inferential: Record<string, boolean>
  charts: Record<string, string[]> | null
  interpretation_style: 'plain' | 'technical' | 'both'
  interpretations: Record<string, string>
  include_data: boolean
  include_variable_dictionary: boolean
}

export interface User {
  id: number
  email: string
  display_name: string | null
  role: 'analyst' | 'developer' | 'admin'
  has_password?: boolean
  google_linked?: boolean
}

export interface ObjectiveAnalysis {
  analysis_type: string
  variables: Assignment
  options: Record<string, unknown>
  filter: { column: string; values: string[] } | null
  title: string
  status?: 'ready' | 'needs_input'
  variables_labels?: Record<string, string | string[]>
}

export interface Objective {
  id: string
  text: string
  subitems?: string[]
  full_text?: string
  analyses: ObjectiveAnalysis[]
  intent: string
  status: 'ready' | 'needs_input'
  question: string | null
  analysis_type?: string
  variables?: Assignment
  options?: Record<string, unknown>
  filter?: { column: string; values: string[] } | null
  title?: string
  assumed: string[]
  variables_labels?: Record<string, string | string[]>
}

export interface BlockAnalysis {
  analysis_type: string
  title: string
  heading?: string
  variables: Assignment
  options: Record<string, unknown>
  filter?: { column: string; values: string[] } | null
  dataset_version_id: number
  configuration_id: number | null
  method?: { description: string }
  settings?: { alpha: number }
  warnings?: string[]
}

export interface ReportBlock {
  id: string
  type: 'heading' | 'table' | 'chart' | 'text'
  include: boolean
  objective_id?: string | null
  title?: string
  title_edited?: boolean
  text?: string | null
  source?: { run_id?: number; table_id?: string; chart_id?: string; field?: string }
  edits?: Record<string, unknown>
  // resolved (read-only, from the server)
  missing?: boolean
  analysis?: BlockAnalysis
  source_table?: ResultTable
  source_chart?: ChartSpec
  resolved?: unknown
  resolved_text?: string
  generated?: { plain: string; technical: string }
  chart_types?: string[]
  alternatives?: { id: string; title: string; type: string }[]
}

export interface Report {
  id: number
  project_id: number
  dataset_id: number | null
  title: string
  objectives: { id: string; text: string; status: string; analysis_type: string | null; run_id: number | null; error: string | null }[]
  options: { style?: 'apa' | 'academic'; decimals?: number; include_details?: boolean; include_methods?: boolean; author?: string; subtitle?: string }
  blocks: ReportBlock[]
  created_at: string
  updated_at: string
}

export interface CompareRequest {
  dataset_id: number
  mode: 'groups' | 'variables'
  group?: string
  levels?: string[]
  measures?: string[]
  var1?: string
  var2?: string
  relation?: 'paired' | 'relationship'
  test?: string
}

export interface ComparePlan {
  analysis_type?: string
  variables?: Assignment
  options?: Record<string, unknown>
  title?: string
  explanation?: string
  question?: { text: string; options: { value: string; label: string }[] }
  dataset_version_id: number
}

export interface DemoPreview {
  key: string
  title: string
  summary: string
  note: string
  objectives: string[]
  columns: string[]
  rows: unknown[][]
  n_rows: number
  results: AnalysisResult[]
}
