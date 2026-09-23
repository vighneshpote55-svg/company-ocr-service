import test from 'node:test';
import assert from 'node:assert/strict';
import React from 'react';
import { renderToString } from 'react-dom/server';
import { SettingsPage } from './SettingsPage.tsx';
import { DashboardLayout } from './DashboardLayout.tsx';
import { AuthProvider } from '../context/AuthContext.tsx';
import type { DashboardStats, DocumentItem, SupportedType } from '../types.ts';

const mockStats: DashboardStats = {
  total: 5,
  ocr_processed: 5,
  ocr_not_required: 0,
  completed: 5,
  failed: 0,
};

const mockDocs: DocumentItem[] = [];
const mockTypes: SupportedType[] = [];

test('SettingsPage renders all 6 navigation tabs with AI Providers as default', () => {
  const html = renderToString(
    React.createElement(
      AuthProvider,
      null,
      React.createElement(SettingsPage, {
        onNotify: () => {},
        stats: mockStats,
        documents: mockDocs,
      })
    )
  );

  // Check 6 Sections in Subnav
  assert.ok(html.includes('AI Providers'), 'Should include AI Providers tab');
  assert.ok(html.includes('Model Settings'), 'Should include Model Settings tab');
  assert.ok(html.includes('Advanced'), 'Should include Advanced tab');
  assert.ok(html.includes('Usage &amp; Quotas') || html.includes('Usage & Quotas'), 'Should include Usage & Quotas tab');
  assert.ok(html.includes('Account &amp; Security') || html.includes('Account & Security'), 'Should include Account & Security tab');
  assert.ok(html.includes('General'), 'Should include General tab');
});

test('SettingsPage renders 5 provider cards: Ollama, OpenAI, Google Gemini, OpenRouter, and Custom AI', () => {
  const html = renderToString(
    React.createElement(
      AuthProvider,
      null,
      React.createElement(SettingsPage, {
        onNotify: () => {},
        stats: mockStats,
        documents: mockDocs,
      })
    )
  );

  assert.ok(html.includes('Ollama (Local)'), 'Must render Ollama card');
  assert.ok(html.includes('OpenAI'), 'Must render OpenAI card');
  assert.ok(html.includes('Google Gemini'), 'Must render Google Gemini card');
  assert.ok(html.includes('OpenRouter'), 'Must render OpenRouter card');
  assert.ok(html.includes('Custom AI Gateway') || html.includes('Custom AI'), 'Must render Custom AI card');
});

test('Custom AI provider card contains Request Format selector and custom endpoint input', () => {
  const html = renderToString(
    React.createElement(
      AuthProvider,
      null,
      React.createElement(SettingsPage, {
        onNotify: () => {},
        stats: mockStats,
        documents: mockDocs,
      })
    )
  );

  assert.ok(html.includes('API Endpoint'), 'Custom card must have endpoint input');
  assert.ok(html.includes('Request Format'), 'Custom card must have format selector');
  assert.ok(html.includes('OpenAI-compatible (/chat/completions)'), 'Must support OpenAI-compatible format');
  assert.ok(html.includes('Ollama Native (/api/chat)'), 'Must support Ollama format');
  assert.ok(html.includes('Raw Prompt (/completions)'), 'Must support completions format');
});

test('API keys are masked with type="password" to protect secrets', () => {
  const html = renderToString(
    React.createElement(
      AuthProvider,
      null,
      React.createElement(SettingsPage, {
        onNotify: () => {},
        stats: mockStats,
        documents: mockDocs,
      })
    )
  );

  // Check that password inputs exist for api keys
  const passwordInputs = html.match(/type="password"/g);
  assert.ok(passwordInputs && passwordInputs.length >= 4, 'Must have password inputs for provider API keys');
});

test('Authenticated users have access to configure and save AI providers', () => {
  const html = renderToString(
    React.createElement(
      AuthProvider,
      null,
      React.createElement(SettingsPage, {
        onNotify: () => {},
        stats: mockStats,
        documents: mockDocs,
      })
    )
  );

  assert.ok(
    html.includes('Activate &amp; Save') || html.includes('Activate & Save'),
    'Authenticated users should have access to Activate & Save provider buttons'
  );
  assert.ok(
    !html.includes('is-read-only'),
    'Settings should not be locked in read-only mode'
  );
});

test('DashboardLayout mounts full-page SettingsPage when currentTab is "settings"', () => {
  const html = renderToString(
    React.createElement(
      AuthProvider,
      null,
      React.createElement(DashboardLayout, {
        mode: 'offline',
        onSelectMode: () => {},
        currentTab: 'settings',
        onSelectTab: () => {},
        isBackendConnected: true,
        isRefreshing: false,
        onRefresh: () => {},
        onOpenSettings: () => {},
        supportedTypes: mockTypes,
        stats: mockStats,
        documents: mockDocs,
        onDocumentUploaded: () => {},
        onDeleteDocument: () => {},
        onSelectDocument: () => {},
        onNotify: () => {},
      })
    )
  );

  assert.ok(html.includes('settings-page-wrapper'), 'Must render settings-page-wrapper');
  assert.ok(html.includes('AI Providers'), 'Must display AI Providers section');
  assert.ok(html.includes('Ollama (Local)'), 'Must display provider cards inside settings tab');
});
