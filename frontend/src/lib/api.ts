import { MetricsSummary, DocumentItem, DocumentChunk, IngestionJob, SystemHealth, Citation, ModelsListResponse } from '@/types';

// Use server-side BFF proxy (/api/proxy) by default in browser to leverage HttpOnly cookies
// or fallback to NEXT_PUBLIC_API_URL if configured for direct connection
const API_BASE_URL =
  typeof window !== 'undefined' && !process.env.NEXT_PUBLIC_FORCE_DIRECT_API
    ? '/api/proxy'
    : process.env.NEXT_PUBLIC_API_URL || 'http://127.0.0.1:8000';

class ApiClient {
  private tenantId: string = 'default-tenant';

  constructor() {
    if (typeof window !== 'undefined') {
      this.tenantId = localStorage.getItem('rag_tenant_id') || 'default-tenant';
      // Clean up any legacy token stored in localStorage
      localStorage.removeItem('rag_token');
    }
  }

  public setTenantId(tenantId: string) {
    this.tenantId = tenantId;
    if (typeof window !== 'undefined') {
      localStorage.setItem('rag_tenant_id', tenantId);
    }
  }

  public setAuth(token: string, tenantId: string) {
    // Retained for backward-compatibility with existing views,
    // but strictly refuses to store the token in localStorage
    this.setTenantId(tenantId);
    if (typeof window !== 'undefined') {
      localStorage.removeItem('rag_token');
    }
  }

  public clearAuth() {
    this.tenantId = 'default-tenant';
    if (typeof window !== 'undefined') {
      localStorage.removeItem('rag_token');
      localStorage.removeItem('rag_tenant_id');
    }
    // Call server-side logout route to clear HttpOnly session cookie
    if (typeof window !== 'undefined') {
      fetch('/api/auth/logout', { method: 'POST' }).catch(() => {});
    }
  }

  public getToken(): string | null {
    // Tokens are HttpOnly cookie-backed; client JS cannot and should not read the raw token
    return null;
  }

  public getTenantId(): string {
    return this.tenantId;
  }

  private headers(isJson = true): Record<string, string> {
    const h: Record<string, string> = {
      'X-Tenant-ID': this.tenantId,
    };
    if (isJson) {
      h['Content-Type'] = 'application/json';
    }
    // Bearer token is NOT sent from browser JS; it is securely attached by the BFF proxy from HttpOnly cookie
    return h;
  }

  public async login(email: string, password: string) {
    const res = await fetch(`${API_BASE_URL}/api/auth/token`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email, password }),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: 'Authentication failed' }));
      throw new Error(err.detail || 'Login failed');
    }
    const data = await res.json();
    if (data.tenant_id) {
      this.setTenantId(data.tenant_id);
    }
    return data;
  }

  public async logout() {
    this.clearAuth();
    await fetch('/api/auth/logout', { method: 'POST' }).catch(() => {});
  }

  public async getHealth(): Promise<SystemHealth> {
    const res = await fetch(`${API_BASE_URL}/api/health`, {
      headers: this.headers(),
    });
    if (!res.ok) throw new Error('Health check failed');
    return res.json();
  }

  public async getMetricsSummary(): Promise<MetricsSummary> {
    const res = await fetch(`${API_BASE_URL}/api/metrics/summary`, {
      headers: this.headers(),
    });
    if (!res.ok) throw new Error('Failed to fetch metrics summary');
    return res.json();
  }

  public async listDocuments(search?: string, limit = 100, offset = 0): Promise<DocumentItem[]> {
    let url = `${API_BASE_URL}/api/documents?limit=${limit}&offset=${offset}`;
    if (search) url += `&search=${encodeURIComponent(search)}`;
    const res = await fetch(url, { headers: this.headers() });
    if (!res.ok) throw new Error('Failed to fetch documents');
    return res.json();
  }

  public async getDocument(id: string): Promise<DocumentItem> {
    const res = await fetch(`${API_BASE_URL}/api/documents/${id}`, {
      headers: this.headers(),
    });
    if (!res.ok) throw new Error('Failed to fetch document');
    return res.json();
  }

  public async getDocumentChunks(id: string): Promise<DocumentChunk[]> {
    const res = await fetch(`${API_BASE_URL}/api/documents/${id}/chunks`, {
      headers: this.headers(),
    });
    if (!res.ok) throw new Error('Failed to fetch chunks');
    return res.json();
  }

  public async deleteDocument(id: string): Promise<void> {
    const res = await fetch(`${API_BASE_URL}/api/documents/${id}`, {
      method: 'DELETE',
      headers: this.headers(),
    });
    if (!res.ok) throw new Error('Failed to delete document');
  }

  public async uploadDocument(file: File): Promise<{ status: string; job_id: string; filename: string }> {
    const formData = new FormData();
    formData.append('file', file);

    const res = await fetch(`${API_BASE_URL}/api/documents/upload`, {
      method: 'POST',
      headers: {
        'X-Tenant-ID': this.tenantId,
      },
      body: formData,
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: 'Upload failed' }));
      throw new Error(err.detail || `Upload failed with HTTP ${res.status}`);
    }
    return res.json();
  }

  public async listPipelineJobs(limit = 50): Promise<IngestionJob[]> {
    const res = await fetch(`${API_BASE_URL}/api/pipeline/jobs?limit=${limit}`, {
      headers: this.headers(),
    });
    if (!res.ok) throw new Error('Failed to fetch pipeline jobs');
    return res.json();
  }

  public async getLLMModels(): Promise<ModelsListResponse> {
    const res = await fetch(`${API_BASE_URL}/api/llm/models`, {
      headers: this.headers(),
    });
    if (!res.ok) throw new Error('Failed to fetch AI models and router status');
    return res.json();
  }

  public async updateLLMConfig(modelId: string, updates: { enabled?: boolean; priority?: number }): Promise<any> {
    const res = await fetch(`${API_BASE_URL}/api/llm/config`, {
      method: 'POST',
      headers: this.headers(true),
      body: JSON.stringify({
        model_id: modelId,
        ...updates
      }),
    });
    if (!res.ok) throw new Error('Failed to update model configuration');
    return res.json();
  }

  public async chatStream(
    query: string,
    options: {
      top_k?: number;
      use_hybrid?: boolean;
      use_rerank?: boolean;
      chat_history?: any[];
      model?: string;
    },
    callbacks: {
      onMessageStart?: (data: any) => void;
      onModelSelected?: (data: { model_id: string; provider: string; tier: string; failover_occurred?: boolean }) => void;
      onCitations?: (citations: Citation[]) => void;
      onToken?: (token: string) => void;
      onComplete?: () => void;
      onError?: (err: string) => void;
    }
  ) {
    const res = await fetch(`${API_BASE_URL}/api/chat/stream`, {
      method: 'POST',
      headers: this.headers(true),
      body: JSON.stringify({
        query,
        top_k: options.top_k ?? 5,
        use_hybrid: options.use_hybrid ?? true,
        use_rerank: options.use_rerank ?? true,
        chat_history: options.chat_history ?? [],
        model: options.model ?? 'qwen/qwen3.8-27b',
      }),
    });

    if (!res.ok) {
      const errText = await res.text();
      callbacks.onError?.(`HTTP ${res.status}: ${errText}`);
      return;
    }

    const reader = res.body?.getReader();
    if (!reader) {
      callbacks.onError?.('Readable stream not supported');
      return;
    }

    const decoder = new TextDecoder();
    let buffer = '';

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split('\n');
      buffer = lines.pop() || '';

      for (const line of lines) {
        const trimmed = line.trim();
        if (trimmed.startsWith('data:')) {
          const raw = trimmed.slice(5).trim();
          try {
            const parsed = JSON.parse(raw);
            if (parsed.type === 'message_start') {
              callbacks.onMessageStart?.(parsed);
            } else if (parsed.type === 'model_selected') {
              callbacks.onModelSelected?.(parsed);
            } else if (parsed.type === 'citations') {
              callbacks.onCitations?.(parsed.citations || []);
            } else if (parsed.type === 'token') {
              callbacks.onToken?.(parsed.token || '');
            } else if (parsed.type === 'message_complete') {
              callbacks.onComplete?.();
            } else if (parsed.type === 'error') {
              callbacks.onError?.(parsed.error || 'Chat stream error');
            }
          } catch (e) {
            console.error('SSE parsing error:', e, raw);
          }
        }
      }
    }
  }
}

export const api = new ApiClient();
