export interface User {
  id: string;
  email: string;
  tenant_id: string;
  role: string;
}

export interface AuthState {
  user: User | null;
  token: string | null;
  tenantId: string;
}

export interface MetricsSummary {
  tenant_id: string;
  total_documents: number;
  total_chunks: number;
  active_jobs_count: number;
  storage_provider: string;
  vector_engine: string;
}

export interface DocumentItem {
  id: string;
  tenant_id: string;
  filename: string;
  file_type: string;
  content_hash: string;
  page_count: number;
  status: string;
  chunk_count: number;
  created_at: string;
}

export interface DocumentChunk {
  id: string;
  document_id: string;
  tenant_id: string;
  chunk_index: number;
  page_number: number;
  chunk_type: string;
  content_text: string;
  qdrant_point_id: string;
  created_at: string;
}

export interface IngestionJob {
  id: string;
  tenant_id: string;
  document_id: string | null;
  status: 'pending' | 'processing' | 'completed' | 'failed';
  progress_percent: number;
  error_message: string | null;
  created_at: string;
  updated_at: string;
}

export interface Citation {
  source: string;
  page: number;
  snippet: string;
  distance: number;
  document_id: string;
  chunk_id: string;
  type: string;
  image_path?: string | null;
}

export interface ChatMessage {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  citations?: Citation[];
  timestamp: string;
  isStreaming?: boolean;
  selectedModel?: string;
  selectedProvider?: string;
  failoverOccurred?: boolean;
}

export interface SystemHealth {
  status: string;
  indexed_documents_count: number;
  vector_store_ready: boolean;
  groq_llm_ready: boolean;
  embedding_model: string;
}

export interface RetrievalResult {
  chunk_id: string;
  document_id: string;
  source: string;
  page: number;
  snippet: string;
  type: string;
  score: number;
  dense_score?: number;
  bm25_score?: number;
  rrf_score?: number;
  rerank_score?: number;
}

export interface ModelDescriptor {
  provider: string;
  model_id: string;
  display_name: string;
  tier: 'free' | 'paid';
  context_window: number;
  max_output_tokens: number;
  supports_multimodal: boolean;
  supports_streaming: boolean;
  priority: number;
  enabled: boolean;
}

export interface ProviderHealth {
  provider: string;
  state: 'closed' | 'open' | 'half_open';
  failure_count: number;
  consecutive_429_count: number;
  last_failure_time?: number | null;
  last_success_time?: number | null;
  cooldown_seconds: number;
  has_credentials: boolean;
  active_key_masked?: string | null;
  available_keys_count: number;
}

export interface ModelsListResponse {
  models: ModelDescriptor[];
  providers: ProviderHealth[];
  active_model_id: string;
}
