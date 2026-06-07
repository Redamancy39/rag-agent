export interface UserRead {
  id: number
  username: string
  email: string | null
  is_active: boolean
  is_admin: boolean
  created_at: string
}

export interface TokenResponse {
  access_token: string
  token_type: string
}

export interface DocumentRead {
  id: number
  filename: string
  file_type: string
  content_type: string | null
  storage_path: string
  file_size: number
  status: string
  status_message: string | null
  chunk_count: number
  error_message: string | null
  owner_id: number
  owner_username: string | null
  created_at: string
  updated_at: string | null
}

export interface DocumentChunkRead {
  id: string
  text: string
  metadata: Record<string, string | number | boolean | null>
  location: SourceLocation | null
}

export interface DocumentProcessingJobRead {
  id: number
  document_id: number
  status: string
  stage: string
  message: string | null
  error_message: string | null
  probe_json: Record<string, unknown> | null
  plan_json: Record<string, unknown> | null
  options_json: Record<string, unknown> | null
  trace_json: IngestionTraceItem[] | null
  progress_total: number
  progress_current: number
  progress_percent: number
  progress_detail: string | null
  created_at: string
  started_at: string | null
  finished_at: string | null
  updated_at: string | null
}

export interface IngestionTraceItem {
  node: string
  label?: string
  state: 'pending' | 'running' | 'done' | 'failed' | 'skipped' | string
  started_at?: string | null
  finished_at?: string | null
  duration_ms?: number | null
  message?: string | null
  error?: string | null
  summary?: Record<string, unknown> | null
  contract?: Record<string, unknown> | null
  state_snapshot?: Record<string, unknown> | null
}

export interface DocumentQualityReportRead {
  document_id: number
  filename: string
  status: string
  status_message: string | null
  total_chunks: number
  unique_pages: number
  unique_locations: number
  chunk_type_counts: Record<string, number>
  quality_counts: Record<string, number>
  average_quality_score: number | null
  health_score: number
  risk_level: string
  risk_items: string[]
  low_quality_count: number
  ocr_chunk_count: number
  ocr_average_score: number | null
  bad_text_layer_count: number
  ocr_replaced_bad_text_layer_count: number
  preprocess_repair_count: number
  suspicious_power_notation_count: number
  table_chunk_count: number
  llm_normalized_count: number
  llm_candidate_count: number
  latest_job_stage: string | null
  latest_job_message: string | null
  latest_job_progress_current: number
  latest_job_progress_total: number
  latest_job_progress_percent: number
  latest_job_trace: IngestionTraceItem[]
  stage_overview: Array<{
    name: string
    state: string
    detail: string
    metric: string
  }>
  recommendations: string[]
}

export interface PermissionRead {
  id: number
  document_id: number
  user_id: number
  user_username: string | null
  can_read: boolean
  can_write: boolean
  created_at: string
}

export interface GroupRead {
  id: number
  name: string
  description: string | null
  created_at: string
}

export interface UserGroupRead {
  id: number
  group_id: number
  user_id: number
  group_name: string | null
  user_username: string | null
  created_at: string
}

export interface GroupPermissionRead {
  id: number
  document_id: number
  group_id: number
  group_name: string | null
  can_read: boolean
  can_write: boolean
  created_at: string
}

export interface AuditLogRead {
  id: number
  actor_user_id: number | null
  action: string
  target_type: string
  target_id: number | null
  document_id: number | null
  user_id: number | null
  group_id: number | null
  detail_json: string | null
  created_at: string
}

export interface SourceLocation {
  kind: string
  key: string
  label: string
  page: number | null
  slide: number | null
  sheet: string | null
  cell_range: string | null
  section_path: string | null
  paragraph_index: number | null
  table_index: number | null
  block_index: number | null
}

export interface Citation {
  citation_id: number | null
  document_id: number
  filename: string
  chunk_id: string | null
  page: number | null
  slide: number | null
  sheet: string | null
  cell_range: string | null
  section_path: string | null
  paragraph_index: number | null
  table_index: number | null
  block_index: number | null
  location: SourceLocation | null
  table: string | null
  chunk_type: string | null
  score: number | null
  text: string
}

export interface AnswerSections {
  classification: string
  conclusion: string
  basis: string
  citation: string
}

export interface EvidenceRow {
  index: number
  score: number | null
  filename: string
  page: number | null
  slide: number | null
  section_path: string | null
  sheet: string | null
  cell_range: string | null
  paragraph_index: number | null
  table_index: number | null
  block_index: number | null
  location: SourceLocation | null
  table: string | null
  chunk_id: string | null
  keywords: string
}

export interface RetrievalTraceHit {
  rank: number
  score: number | null
  filename: string
  page: number | null
  slide: number | null
  section_path: string | null
  sheet: string | null
  cell_range: string | null
  paragraph_index: number | null
  table_index: number | null
  block_index: number | null
  location: SourceLocation | null
  table: string | null
  chunk_id: string | null
  retrieval_source: string | null
  matched_terms: string[]
}

export interface RetrievalTraceStep {
  query_index: number
  query: string
  source: string
  hit_count: number
  top_hits: RetrievalTraceHit[]
}

export interface QueryPlanRead {
  original_question: string
  normalized_question: string
  needs_rewrite: boolean
  question_type: string
  source: string
  reason: string
  standard_refs: string[]
  entities: string[]
  metrics: string[]
  sub_questions: string[]
  rewritten_queries: string[]
  evidence_requirements: string[]
  synonym_expansions: Array<Record<string, unknown>>
  confidence: number
  llm_used: boolean
  warnings: string[]
}

export interface EvidenceDecisionRead {
  sufficient: boolean
  source: string
  reason: string
  confidence: number
  missing_requirements: string[]
  warnings: string[]
}

export interface CitationValidationRead {
  valid: boolean
  cited_indices: number[]
  invalid_indices: number[]
  uncited_sections: string[]
  warnings: string[]
}

export interface ChatResponse {
  answer: string
  sections: AnswerSections
  evidence_rows: EvidenceRow[]
  citations: Citation[]
  retrieval_trace: RetrievalTraceStep[]
  query_plan: QueryPlanRead | null
  evidence_decision: EvidenceDecisionRead | null
  citation_validation: CitationValidationRead
  retrieval_only: boolean
  log_id: number | null
}

export interface ChatJobRead {
  id: number
  user_id: number
  status: string
  stage: string
  message: string | null
  error_message: string | null
  question: string
  document_ids_json: number[] | null
  top_k: number
  progress_percent: number
  progress_detail: string | null
  trace_json: Array<Record<string, unknown>> | null
  response_json: ChatResponse | null
  log_id: number | null
  created_at: string
  started_at: string | null
  finished_at: string | null
  updated_at: string | null
}

export interface ChatLogRead {
  id: number
  user_id: number
  question: string
  answer: string
  citations_json: string | null
  created_at: string
}

export interface UploadProgressItem {
  id: string
  document_id?: number
  filename: string
  progress: number
  status: 'ready' | 'uploading' | 'indexing' | 'success' | 'error'
  message: string
  stageLabel?: string
  progressCurrent?: number
  progressTotal?: number
}
