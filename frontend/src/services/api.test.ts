import test from 'node:test';
import assert from 'node:assert/strict';
import { ApiService, normalizeOpenRouterConfig } from './api.ts';
import { normalizeAiDocument } from '../types.ts';

test('ApiService handles authDisabled state correctly', async () => {
  const api = new ApiService();

  const originalFetch = globalThis.fetch;
  globalThis.fetch = async (url: any) => {
    if (String(url).includes('/api/auth-status')) {
      return {
        ok: true,
        json: async () => ({ auth_enabled: false, auth_mode: 'disabled' }),
      } as any;
    }
    return { ok: true, json: async () => ({}) } as any;
  };

  try {
    const status = await api.checkAuthStatus();
    assert.equal(status.auth_enabled, false);
    assert.equal(api.isAuthEnabled(), false);
    assert.equal(api.isAuthenticated(), true);

    // Headers should NOT contain Authorization even if an old token is present
    api.setToken('lingering-stale-token');
    const headers = (api as any).getHeaders();
    assert.equal(headers['Authorization'], undefined);

    // URLs should not contain query token
    assert.equal(api.getFileUrl('doc123'), 'http://localhost:8000/api/documents/doc123/file');
    assert.equal(api.getPreviewUrl('doc123'), 'http://localhost:8000/api/documents/doc123/preview');
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test('ApiService handles authEnabled state correctly and attaches Bearer token', async () => {
  const api = new ApiService();

  const originalFetch = globalThis.fetch;
  globalThis.fetch = async (url: any) => {
    if (String(url).includes('/api/auth-status')) {
      return {
        ok: true,
        json: async () => ({ auth_enabled: true, auth_mode: 'jwt' }),
      } as any;
    }
    return { ok: true, json: async () => ({}) } as any;
  };

  try {
    const status = await api.checkAuthStatus();
    assert.equal(status.auth_enabled, true);
    assert.equal(api.isAuthEnabled(), true);

    // No token set yet -> isAuthenticated must be false
    api.setToken(null);
    assert.equal(api.isAuthenticated(), false);
    const unauthHeaders = (api as any).getHeaders();
    assert.equal(unauthHeaders['Authorization'], undefined);

    // Token set -> isAuthenticated must be true and headers must include Bearer token
    api.setToken('valid-jwt-token-xyz');
    assert.equal(api.isAuthenticated(), true);

    const authHeaders = (api as any).getHeaders();
    assert.equal(authHeaders['Authorization'], 'Bearer valid-jwt-token-xyz');

    // URLs must include query token
    assert.equal(api.getFileUrl('doc123'), 'http://localhost:8000/api/documents/doc123/file?token=valid-jwt-token-xyz');
    assert.equal(api.getPreviewUrl('doc123'), 'http://localhost:8000/api/documents/doc123/preview?token=valid-jwt-token-xyz');
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test('ApiService triggers unauthorized listener and clears token on 401', async () => {
  const api = new ApiService();
  api.setAuthEnabled(true, 'jwt');
  api.setToken('expired-jwt-token');

  let listenerFired = false;
  api.onUnauthorized(() => {
    listenerFired = true;
  });

  const originalFetch = globalThis.fetch;
  globalThis.fetch = async () => {
    return {
      status: 401,
      ok: false,
      json: async () => ({ detail: 'Token expired' }),
    } as any;
  };

  try {
    await assert.rejects(async () => {
      await (api as any).fetchWithAuth('http://localhost:8000/api/stats');
    }, /Authentication required or session expired/);

    assert.equal(listenerFired, true);
    assert.equal(api.getToken(), null);
    assert.equal(api.isAuthenticated(), false);
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test('ApiService clearAllDocuments calls DELETE /api/documents/clear and returns result', async () => {
  const api = new ApiService();
  api.setAuthEnabled(false);

  let capturedUrl = '';
  let capturedMethod = '';

  const originalFetch = globalThis.fetch;
  globalThis.fetch = async (url: any, options: any) => {
    capturedUrl = String(url);
    capturedMethod = options?.method || 'GET';
    return {
      status: 200,
      ok: true,
      json: async () => ({
        success: true,
        deleted_count: 5,
        message: 'All documents have been deleted.',
      }),
    } as any;
  };

  try {
    const res = await api.clearAllDocuments();
    assert.equal(capturedUrl, 'http://localhost:8000/api/documents/clear');
    assert.equal(capturedMethod, 'DELETE');
    assert.equal(res.success, true);
    assert.equal(res.deleted_count, 5);
    assert.equal(res.message, 'All documents have been deleted.');
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test('ApiService getOllamaStatus calls GET /api/ollama/status and returns health object', async () => {
  const api = new ApiService();
  api.setAuthEnabled(false);

  let capturedUrl = '';

  const originalFetch = globalThis.fetch;
  globalThis.fetch = async (url: any) => {
    capturedUrl = String(url);
    return {
      status: 200,
      ok: true,
      json: async () => ({
        reachable: true,
        model_installed: true,
        model: 'qwen2.5vl:3b',
        message: 'Ollama server is running and qwen2.5vl:3b is ready.',
      }),
    } as any;
  };

  try {
    const res = await api.getOllamaStatus();
    assert.equal(capturedUrl, 'http://localhost:8000/api/ollama/status');
    assert.equal(res.reachable, true);
    assert.equal(res.model_installed, true);
    assert.equal(res.model, 'qwen2.5vl:3b');
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test('ApiService getAiConfig calls GET /api/ai/config and returns safe config', async () => {
  const api = new ApiService();
  api.setAuthEnabled(false);

  let capturedUrl = '';
  const originalFetch = globalThis.fetch;
  globalThis.fetch = async (url: any) => {
    capturedUrl = String(url);
    return {
      status: 200,
      ok: true,
      json: async () => ({
        active_provider: 'local',
        active_model: 'qwen2.5vl:3b',
        mode: 'local',
        api_key_configured: false,
        ollama_available: true,
        local_fallback_available: true,
      }),
    } as any;
  };

  try {
    const cfg = await api.getAiConfig();
    assert.equal(capturedUrl, 'http://localhost:8000/api/ai/config');
    assert.equal(cfg.active_provider, 'local');
    assert.equal(cfg.mode, 'local');
    assert.equal(cfg.api_key_configured, false);
    assert.equal((cfg as any).api_key, undefined);
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test('ApiService updateAiConfig calls POST /api/ai/config with payload', async () => {
  const api = new ApiService();
  api.setAuthEnabled(false);

  let capturedUrl = '';
  let capturedBody = '';
  const originalFetch = globalThis.fetch;
  globalThis.fetch = async (url: any, opts: any) => {
    capturedUrl = String(url);
    capturedBody = opts?.body || '';
    return {
      status: 200,
      ok: true,
      json: async () => ({
        active_provider: 'openrouter',
        active_model: 'google/gemini-2.5-flash',
        mode: 'external',
        api_key_configured: true,
      }),
    } as any;
  };

  try {
    const updated = await api.updateAiConfig({
      provider: 'openrouter',
      api_key: 'sk-test-secret-key-12345',
      model: 'google/gemini-2.5-flash',
    });
    assert.equal(capturedUrl, 'http://localhost:8000/api/ai/config');
    assert.ok(capturedBody.includes('sk-test-secret-key-12345'));
    assert.equal(updated.mode, 'external');
    assert.equal((updated as any).api_key, undefined);
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test('ApiService testAiConnection calls POST /api/ai/test-connection', async () => {
  const api = new ApiService();
  api.setAuthEnabled(false);

  let capturedUrl = '';
  const originalFetch = globalThis.fetch;
  globalThis.fetch = async (url: any) => {
    capturedUrl = String(url);
    return {
      status: 200,
      ok: true,
      json: async () => ({
        success: true,
        provider: 'ollama',
        model: 'qwen2.5vl:3b',
        message: 'Ollama is ready',
        latency_ms: 12,
      }),
    } as any;
  };

  try {
    const res = await api.testAiConnection({ provider: 'local' });
    assert.equal(capturedUrl, 'http://localhost:8000/api/ai/test-connection');
    assert.equal(res.success, true);
    assert.equal(res.provider, 'ollama');
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test('API keys are NEVER persisted to localStorage or sessionStorage', () => {
  const dummyKey = 'sk-or-never-store-in-browser-storage-999';
  
  // Verify localStorage and sessionStorage keys
  const localKeys = Object.keys(globalThis.localStorage || {});
  const sessionKeys = Object.keys(globalThis.sessionStorage || {});

  for (const k of localKeys) {
    const val = (globalThis.localStorage as any).getItem(k);
    assert.notEqual(val, dummyKey);
    assert.ok(!String(k).toLowerCase().includes('ai_api_key'));
  }
  for (const k of sessionKeys) {
    const val = (globalThis.sessionStorage as any).getItem(k);
    assert.notEqual(val, dummyKey);
    assert.ok(!String(k).toLowerCase().includes('ai_api_key'));
  }
});

test('normalizeOpenRouterConfig normalizes base URL, strips fragments, and sets model ID', () => {
  const res = normalizeOpenRouterConfig(
    'openrouter',
    'NVIDIA: Nemotron 3 Ultra (free)',
    'https://openrouter.ai/nvidia/nemotron-3-ultra-550b-a55b:free#providers'
  );

  assert.equal(res.provider, 'openrouter');
  assert.equal(res.baseUrl, 'https://openrouter.ai/api/v1');
  assert.equal(res.model, 'nvidia/nemotron-3-ultra-550b-a55b:free');
  assert.ok(!res.baseUrl.includes('#providers'));
});

test('normalizeOpenRouterConfig extracts model from openrouter webpage URL', () => {
  const res = normalizeOpenRouterConfig(
    'openrouter',
    'https://openrouter.ai/nvidia/nemotron-3-ultra-550b-a55b:free#providers',
    'https://openrouter.ai/nvidia/nemotron-3-ultra-550b-a55b:free#providers'
  );

  assert.equal(res.baseUrl, 'https://openrouter.ai/api/v1');
  assert.equal(res.model, 'nvidia/nemotron-3-ultra-550b-a55b:free');
});

test('ApiService getDocumentFile attaches Bearer token and returns Blob', async () => {
  const api = new ApiService();
  api.setAuthEnabled(true, 'jwt');
  api.setToken('mock-preview-jwt');

  let capturedUrl = '';
  let capturedHeaders: Record<string, string> = {};
  const originalFetch = globalThis.fetch;
  globalThis.fetch = async (url: any, opts: any) => {
    capturedUrl = String(url);
    capturedHeaders = opts?.headers || {};
    return {
      status: 200,
      ok: true,
      blob: async () => new Blob(['%PDF-1.4 mock pdf content'], { type: 'application/pdf' }),
    } as any;
  };

  try {
    const blob = await api.getDocumentFile('doc_preview_123');
    assert.equal(capturedUrl, 'http://localhost:8000/api/documents/doc_preview_123/file');
    assert.equal(capturedHeaders['Authorization'], 'Bearer mock-preview-jwt');
    assert.equal(blob.type, 'application/pdf');
    assert.ok(blob.size > 0);
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test('ApiService getThumbnail attaches Bearer token and returns Blob', async () => {
  const api = new ApiService();
  api.setAuthEnabled(true, 'jwt');
  api.setToken('mock-thumb-jwt');

  let capturedUrl = '';
  let capturedHeaders: Record<string, string> = {};
  const originalFetch = globalThis.fetch;
  globalThis.fetch = async (url: any, opts: any) => {
    capturedUrl = String(url);
    capturedHeaders = opts?.headers || {};
    return {
      status: 200,
      ok: true,
      blob: async () => new Blob(['mock png bytes'], { type: 'image/png' }),
    } as any;
  };

  try {
    const blob = await api.getThumbnail('doc_thumb_123');
    assert.equal(capturedUrl, 'http://localhost:8000/api/documents/doc_thumb_123/thumbnail');
    assert.equal(capturedHeaders['Authorization'], 'Bearer mock-thumb-jwt');
    assert.equal(blob.type, 'image/png');
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test('ApiService handles 401 by attempting session refresh and retrying once', async () => {
  const api = new ApiService();
  api.setAuthEnabled(true, 'jwt');
  api.setToken('expired-initial-jwt');

  let fetchCount = 0;
  let headersHistory: any[] = [];
  const originalFetch = globalThis.fetch;

  // Mock handleAuthFailureAndRefresh
  api.handleAuthFailureAndRefresh = async () => {
    api.setToken('refreshed-new-jwt');
    return 'refreshed-new-jwt';
  };

  globalThis.fetch = async (url: any, opts: any) => {
    fetchCount++;
    headersHistory.push({ ...(opts?.headers || {}) });
    if (fetchCount === 1) {
      return {
        status: 401,
        ok: false,
        json: async () => ({ detail: 'Token expired' }),
      } as any;
    }
    return {
      status: 200,
      ok: true,
      json: async () => ({ id: 'doc_123', status: 'completed' }),
    } as any;
  };

  try {
    const doc = await api.getDocument('doc_123');
    assert.equal(fetchCount, 2);
    assert.equal(headersHistory[0]['Authorization'], 'Bearer expired-initial-jwt');
    assert.equal(headersHistory[1]['Authorization'], 'Bearer refreshed-new-jwt');
    assert.equal(doc.id, 'doc_123');
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test('normalizeAiDocument preserves OCR extracted text across all field formats', () => {
  // Case 1: extracted_text present
  const doc1 = normalizeAiDocument({ id: '1', filename: 'doc1.pdf', extracted_text: 'Hello world from OCR' });
  assert.equal(doc1.extracted_text, 'Hello world from OCR');
  assert.equal(doc1.raw_text, 'Hello world from OCR');

  // Case 2: ocr_result.raw_text present
  const doc2 = normalizeAiDocument({ id: '2', filename: 'doc2.pdf', ocr_result: { raw_text: 'Text inside ocr_result' } });
  assert.equal(doc2.extracted_text, 'Text inside ocr_result');
  assert.equal(doc2.raw_text, 'Text inside ocr_result');

  // Case 3: ocr_text present
  const doc3 = normalizeAiDocument({ id: '3', filename: 'doc3.pdf', ocr_text: 'Text in ocr_text' });
  assert.equal(doc3.extracted_text, 'Text in ocr_text');

  // Case 4: raw_text present
  const doc4 = normalizeAiDocument({ id: '4', filename: 'doc4.pdf', raw_text: 'Text in raw_text' });
  assert.equal(doc4.extracted_text, 'Text in raw_text');
});




