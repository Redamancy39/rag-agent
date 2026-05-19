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
  progress_total: number
  progress_current: number
  progress_percent: number
  progress_detail: string | null
  created_at: string
  started_at: string | null
  finished_at: string | null
  updated_at: string | null
}

export interface DocumentQualityReportRead {
  document_id: number
  filename: string
  status: string
  status_message: string | null
  total_chunks: number
  unique_pages: number
  chunk_type_counts: Record<string, number>
  quality_counts: Record<string, number>
  average_quality_score: number | null
  low_quality_count: number
  ocr_chunk_count: number
  ocr_average_score: number | null
  table_chunk_count: number
  llm_normalized_count: number
  llm_candidate_count: number
  latest_job_stage: string | null
  latest_job_message: string | null
  latest_job_progress_current: number
  latest_job_progress_total: number
  latest_job_progress_percent: number
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

export interface Citation {
  document_id: number
  filename: string
  chunk_id: string | null
  page: number | null
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
  table: string | null
  chunk_id: string | null
  keywords: string
}

export interface ChatResponse {
  answer: string
  sections: AnswerSections
  evidence_rows: EvidenceRow[]
  citations: Citation[]
  retrieval_only: boolean
  log_id: number | null
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
