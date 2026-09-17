import test from 'node:test';
import assert from 'node:assert/strict';
import { ApiService } from './api.ts';

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


