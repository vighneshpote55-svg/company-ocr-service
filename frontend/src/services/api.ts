import type { DocumentItem, DashboardStats, SupportedType, AuthConfig, EngineInfo } from '../types';

const STORAGE_KEY_AUTH = 'ocr_app_auth_config';

export function getStoredAuthConfig(): AuthConfig {
  try {
    const raw = localStorage.getItem(STORAGE_KEY_AUTH);
    if (raw) {
      return JSON.parse(raw);
    }
  } catch (e) {
    // Ignore parse error
  }
  return {
    baseUrl: window.location.port === '5173' ? 'http://localhost:8000' : window.location.origin,
    authMode: 'none',
    clientId: 'test-client',
    clientSecret: 'test-secret',
  };
}

export function saveStoredAuthConfig(cfg: AuthConfig): void {
  localStorage.setItem(STORAGE_KEY_AUTH, JSON.stringify(cfg));
}

export class ApiService {
  private config: AuthConfig;

  constructor() {
    this.config = getStoredAuthConfig();
  }

  public updateConfig(newConfig: Partial<AuthConfig>) {
    this.config = { ...this.config, ...newConfig };
    saveStoredAuthConfig(this.config);
  }

  public getConfig(): AuthConfig {
    return this.config;
  }

  private getHeaders(isFormData = false): Record<string, string> {
    const headers: Record<string, string> = {};
    if (!isFormData) {
      headers['Content-Type'] = 'application/json';
    }

    if (this.config.token) {
      headers['Authorization'] = `Bearer ${this.config.token}`;
    }
    if (this.config.apiKey) {
      headers['X-API-Key'] = this.config.apiKey;
    }

    return headers;
  }

  private getUrl(path: string): string {
    const base = this.config.baseUrl.replace(/\/+$/, '');
    return `${base}${path.startsWith('/') ? path : '/' + path}`;
  }

  public async checkHealth(): Promise<{ status: string; version: string }> {
    const res = await fetch(this.getUrl('/health'), {
      headers: this.getHeaders(),
    });
    if (!res.ok) {
      throw new Error(`Server returned HTTP ${res.status}`);
    }
    return res.json();
  }

  public async getEngineInfo(): Promise<EngineInfo> {
    const res = await fetch(this.getUrl('/engine-info'), {
      headers: this.getHeaders(),
    });
    if (!res.ok) {
      throw new Error(`Failed to load engine info (HTTP ${res.status})`);
    }
    return res.json();
  }

  public async mintToken(clientId: string, clientSecret: string): Promise<string> {
    const formData = new URLSearchParams();
    formData.append('client_id', clientId);
    formData.append('client_secret', clientSecret);

    const res = await fetch(this.getUrl('/auth/token'), {
      method: 'POST',
      headers: {
        'Content-Type': 'application/x-www-form-urlencoded',
      },
      body: formData.toString(),
    });

    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: 'Failed to mint token' }));
      throw new Error(err.detail || `Auth failed with HTTP ${res.status}`);
    }

    const data = await res.json();
    this.updateConfig({ token: data.access_token });
    return data.access_token;
  }

  public async getSupportedTypes(): Promise<SupportedType[]> {
    const res = await fetch(this.getUrl('/api/supported-types'), {
      headers: this.getHeaders(),
    });
    if (!res.ok) throw new Error('Failed to load supported document types');
    return res.json();
  }

  public async getStats(): Promise<DashboardStats> {
    const res = await fetch(this.getUrl('/api/stats'), {
      headers: this.getHeaders(),
    });
    if (!res.ok) throw new Error('Failed to load dashboard statistics');
    return res.json();
  }

  public async getDocuments(params?: {
    search?: string;
    docType?: string;
    ocrRequired?: boolean;
    status?: string;
    limit?: number;
    offset?: number;
  }): Promise<{ items: DocumentItem[]; total: number }> {
    const query = new URLSearchParams();
    if (params?.search) query.set('search', params.search);
    if (params?.docType && params.docType !== 'all') query.set('doc_type', params.docType);
    if (params?.ocrRequired !== undefined) query.set('ocr_required', String(params.ocrRequired));
    if (params?.status && params.status !== 'all') query.set('status', params.status);
    if (params?.limit) query.set('limit', String(params.limit));
    if (params?.offset) query.set('offset', String(params.offset));

    const url = this.getUrl(`/api/documents?${query.toString()}`);
    const res = await fetch(url, { headers: this.getHeaders() });
    if (!res.ok) throw new Error('Failed to load documents');
    return res.json();
  }

  public async getDocument(docId: string): Promise<DocumentItem> {
    const res = await fetch(this.getUrl(`/api/documents/${docId}`), {
      headers: this.getHeaders(),
    });
    if (!res.ok) throw new Error('Document not found');
    return res.json();
  }

  public async deleteDocument(docId: string): Promise<boolean> {
    const res = await fetch(this.getUrl(`/api/documents/${docId}`), {
      method: 'DELETE',
      headers: this.getHeaders(),
    });
    return res.ok;
  }

  public async uploadDocument(
    file: File,
    docType?: string,
    expectedData?: string,
    onProgress?: (percent: number) => void
  ): Promise<DocumentItem> {
    const formData = new FormData();
    formData.append('file', file);
    if (docType && docType !== 'auto') {
      formData.append('doc_type', docType);
    }
    if (expectedData) {
      formData.append('expected_data', expectedData);
    }

    // Use XMLHttpRequest for live upload progress
    return new Promise((resolve, reject) => {
      const xhr = new XMLHttpRequest();
      xhr.open('POST', this.getUrl('/api/upload'));

      if (this.config.token) {
        xhr.setRequestHeader('Authorization', `Bearer ${this.config.token}`);
      }
      if (this.config.apiKey) {
        xhr.setRequestHeader('X-API-Key', this.config.apiKey);
      }

      xhr.upload.onprogress = (evt) => {
        if (evt.lengthComputable && onProgress) {
          const pct = Math.round((evt.loaded / evt.total) * 60); // 0-60% for transfer
          onProgress(pct);
        }
      };

      xhr.onload = () => {
        if (xhr.status >= 200 && xhr.status < 300) {
          try {
            if (onProgress) onProgress(100);
            const data = JSON.parse(xhr.responseText);
            resolve(data);
          } catch (e) {
            reject(new Error('Invalid JSON returned by server'));
          }
        } else {
          try {
            const err = JSON.parse(xhr.responseText);
            reject(new Error(err.detail || `Upload failed: ${xhr.statusText}`));
          } catch {
            reject(new Error(`Upload failed with status ${xhr.status}`));
          }
        }
      };

      xhr.onerror = () => {
        reject(new Error('Network error during upload'));
      };

      xhr.send(formData);
    });
  }

  public getFileUrl(docId: string, download = false): string {
    return this.getUrl(`/api/documents/${docId}/file${download ? '?download=true' : ''}`);
  }

  public getPreviewUrl(docId: string): string {
    return this.getUrl(`/api/documents/${docId}/preview`);
  }
}

export const api = new ApiService();
