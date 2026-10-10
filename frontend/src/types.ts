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

export interface DocumentLlmStatus {
  screening_status: string
  check_status: string
  normalization_status: string
  candidate_count: number | null
  attempted_count: number | null
  succeeded_count: number | null
  failed_count: number | null
  generated_count: number | null
  stored_count: number | null
  processed_count?: number | null
  skipped_count?: number | null
  request_attempted_count?: number | null
  request_succeeded_count?: number | null
  request_failed_count?: number | null
  retry_count?: number | null
  request_max_calls?: number | null
  elapsed_seconds?: number | null
  limit_reason?: string | null
  job_id: number | null
  checked_at: string | null
  detail: string
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
  collection_id: number | null
  collection_name: string | null
  created_at: string
  updated_at: string | null
  llm_processing?: DocumentLlmStatus
}

export interface DocumentUploadRead extends DocumentRead {
  duplicate: boolean
  duplicate_reason: string | null
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

export interface DocumentCollectionRead {
  id: number
  name: string
  description: string | null
  owner_id: number
  owner_username: string | null
  document_count: number
  can_read: boolean
  can_write: boolean
  created_at: string
  updated_at: string | null
}

export interface CollectionUserPermissionRead {
  id: number
  collection_id: number
  user_id: number
  user_username: string | null
  can_read: boolean
  can_write: boolean
  created_at: string
}

export interface CollectionGroupPermissionRead {
  id: number
  collection_id: number
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
  collection_id: number | null
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
  vector_score: number | null
  keyword_score: number | null
  bm25_score: number | null
  raw_bm25_score: number | null
  pre_rerank_score: number | null
  rerank_score: number | null
  distance: number | null
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
  preserved_from_pre_rerank: boolean
  selected_for_answer: boolean
  citation_id: number | null
  text_preview: string
}

export interface RetrievalTraceStep {
  query_index: number
  query: string
  source: string
  hit_count: number
  duration_ms: number | null
  top_hits: RetrievalTraceHit[]
}

export interface HotwordMatch {
  original: string
  term: string
  category: string
  start: number
  end: number
  kind: 'term' | 'alias'
}

export interface QueryCorrection {
  original: string
  replacement: string
  start: number
  end: number
  reason: string
}

export interface QuerySuggestion {
  original: string
  candidates: string[]
  start: number
  end: number
  reason: string
}

export interface QueryPreviewRead {
  original_question: string
  corrected_question: string
  normalized_question: string
  lexicon_version: string
  hotword_matches: HotwordMatch[]
  corrections: QueryCorrection[]
  suggestions: QuerySuggestion[]
}

export interface HotwordCatalogue {
  version: string
  categories: Record<string, string>
  entries: Array<{term: string; category: string; aliases: string[]; typos: string[]; source: {title: string; url: string}}>
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
  corrected_question?: string
  lexicon_version?: string
  hotword_matches?: HotwordMatch[]
  corrections?: QueryCorrection[]
  suggestions?: QuerySuggestion[]
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

export interface RetrievalScopeRead {
  requested_document_ids: number[]
  allowed_document_ids: number[]
  top_k: number
  options?: {
    top_k: number; rerank_enabled: boolean; candidate_top_k: number; context_auto: boolean
    context_max_chars: number; model_context_tokens: number; output_reserve_ratio: number; max_output_tokens: number
  } | null
  usage?: {
    retrieved_count: number; usable_count: number; context_evidence_count: number; context_chars: number
    omitted_count: number; rerank_applied: boolean; generation_requested: boolean
    input_token_upper_bound: number | null; token_estimate_method: string
    input_tokens: number | null; output_tokens: number | null; reasoning_tokens: number | null
    output_limit_reached: boolean; effective_max_output_tokens: number | null; budget_message: string | null
  } | null
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
  retrieval_scope: RetrievalScopeRead
  retrieval_only: boolean
  knowledge_search?: boolean
  knowledge_search_reason?: string | null
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
  retrieval_trace: RetrievalTraceStep[]
  query_plan: QueryPlanRead | null
  evidence_decision: EvidenceDecisionRead | null
  citation_validation: CitationValidationRead
  retrieval_scope: RetrievalScopeRead
  response: ChatResponse | null
  created_at: string
}

export interface UploadProgressItem {
  id: string
  document_id?: number
  duplicate?: boolean
  filename: string
  relativePath?: string
  progress: number
  status: 'ready' | 'uploading' | 'indexing' | 'success' | 'error'
  message: string
  stageLabel?: string
  progressCurrent?: number
  progressTotal?: number
  jobUpdatedAt?: string | null
}
