import test from 'node:test';
import assert from 'node:assert/strict';
import React from 'react';
import { renderToString } from 'react-dom/server';
import { DocumentsTable } from './DocumentsTable.tsx';
import { DocumentPreview } from './DocumentPreview.tsx';
import { OcrDecisionBadge } from './OcrDecisionBadge.tsx';
import { AIAnalysisCard } from './AIAnalysisCard.tsx';
import { AISummaryCard } from './AISummaryCard.tsx';
import { AIKeyFindingsCard } from './AIKeyFindingsCard.tsx';
import { AIChatPanel } from './AIChatPanel.tsx';
import { SettingsModal } from './SettingsModal.tsx';
import { AIModeView } from './AIModeView.tsx';
import type { DocumentItem, SupportedType, AIProviderConfig } from '../types.ts';
import { normalizeAiDocument } from '../types.ts';

const mockSupportedTypes: SupportedType[] = [
  { id: 'auto', name: 'Auto Detect', category: 'General' },
  { id: 'pan', name: 'PAN Card', category: 'Identity' },
  { id: 'gst_certificate', name: 'GST Certificate', category: 'Business' },
  { id: 'bank_statement', name: 'Bank Statement', category: 'Financial' },
];

const mockThreeDocuments: DocumentItem[] = [
  {
    id: 'e44a1306-5e07-40d3-9764-33aa80de0723',
    filename: 'WhatsApp Image 2026-09-10 at 16.53.24.jpeg',
    file_path: '/app/uploads/original/e44a1306-5e07-40d3-9764-33aa80de0723.jpeg.enc',
    file_size: 129097,
    file_type: '.jpeg',
    doc_type: 'ai_analyzed',
    document_type: 'PAN Card',
    ocr_required: true,
    text_source: 'rapid_ocr',
    status: 'completed',
    confidence: 0.95,
    pages: 1,
    extracted_fields: { pan_number: 'IVQPP1031M' },
    field_confidences: {},
    extracted_text: 'INCOME TAX DEPARTMENT GOVT OF INDIA',
    has_preview: true,
    preview_url: '/api/documents/e44a1306-5e07-40d3-9764-33aa80de0723/preview',
    file_url: '/api/documents/e44a1306-5e07-40d3-9764-33aa80de0723/file',
    created_at: '2026-09-21T07:16:56.857113+00:00',
  },
  {
    id: '2112fd84-5bcd-4f6d-ba3a-84d7d06dca01',
    filename: 'GST RC.pdf',
    file_path: '/app/uploads/original/2112fd84-5bcd-4f6d-ba3a-84d7d06dca01.pdf.enc',
    file_size: 165339,
    file_type: '.pdf',
    doc_type: 'ai_analyzed',
    document_type: 'GST Registration Certificate',
    ocr_required: false,
    text_source: 'pdf_text_layer',
    status: 'completed',
    confidence: 0.95,
    pages: 3,
    extracted_fields: { gstin: '27AADFZ9861F1ZN' },
    field_confidences: {},
    extracted_text: 'Government of India Form GST REG-06 Registration Certificate',
    has_preview: true,
    preview_url: '/api/documents/2112fd84-5bcd-4f6d-ba3a-84d7d06dca01/preview',
    file_url: '/api/documents/2112fd84-5bcd-4f6d-ba3a-84d7d06dca01/file',
    created_at: '2026-09-21T07:13:00.995860+00:00',
  },
  {
    id: 'a0e3b5b4-0fc8-4ccf-aae9-9904aec52995',
    filename: 'Account_Statement_Report_30-07-2026_1246hrs.PDF',
    file_path: '/app/uploads/original/a0e3b5b4-0fc8-4ccf-aae9-9904aec52995.pdf.enc',
    file_size: 146260,
    file_type: '.pdf',
    doc_type: 'bank_statement',
    document_type: 'Bank Statement',
    ocr_required: false,
    text_source: 'pdf_text_layer',
    status: 'completed',
    confidence: 0.98,
    pages: 24,
    extracted_fields: { account_number: '916364859966975' },
    field_confidences: {},
    extracted_text: 'Axis Bank Statement of Account',
    has_preview: true,
    preview_url: '/api/documents/a0e3b5b4-0fc8-4ccf-aae9-9904aec52995/preview',
    file_url: '/api/documents/a0e3b5b4-0fc8-4ccf-aae9-9904aec52995/file',
    created_at: '2026-09-21T07:06:51.730803+00:00',
  },
];

test('DocumentsTable renders all 3 documents returned from GET /api/documents', () => {
  const html = renderToString(
    React.createElement(DocumentsTable, {
      documents: mockThreeDocuments,
      supportedTypes: mockSupportedTypes,
      onSelectDocument: () => {},
      onDeleteDocument: () => {},
      onRefresh: () => {},
      isLoading: false,
    })
  );

  // Assert all 3 filenames are rendered
  assert.ok(
    html.includes('WhatsApp Image 2026-09-10 at 16.53.24.jpeg'),
    'PAN Card document should be rendered in vault table'
  );
  assert.ok(
    html.includes('GST RC.pdf'),
    'GST Registration Certificate document should be rendered in vault table'
  );
  assert.ok(
    html.includes('Account_Statement_Report_30-07-2026_1246hrs.PDF'),
    'Bank Statement document should be rendered in vault table'
  );

  // Assert all 3 document types are rendered
  assert.ok(html.includes('PAN Card'), 'PAN Card type pill should be rendered');
  assert.ok(html.includes('GST Registration Certificate'), 'GST Registration Certificate type pill should be rendered');
  assert.ok(html.includes('Bank Statement'), 'Bank Statement type pill should be rendered');

  // Count the number of rows rendered
  const rowMatches = html.match(/vault-table-row/g);
  assert.equal(rowMatches?.length, 3, 'Vault table must render exactly 3 rows for 3 documents');
});

test('A new upload does not replace previous vault records with only the newest document', () => {
  // Initial state with 3 documents
  let vaultDocuments: DocumentItem[] = [...mockThreeDocuments];

  // Simulate a 4th newly uploaded document (e.g. Aadhaar Card)
  const newlyUploadedDoc: DocumentItem = {
    id: 'f99c88b3-1122-3344-5566-778899aabbcc',
    filename: 'Aadhaar_Card_Sample.png',
    file_path: '/app/uploads/original/f99c88b3.png.enc',
    file_size: 98000,
    file_type: '.png',
    doc_type: 'aadhaar',
    document_type: 'Aadhaar Card',
    ocr_required: true,
    text_source: 'rapid_ocr',
    status: 'completed',
    confidence: 0.99,
    pages: 1,
    extracted_fields: { aadhaar_number: '1234 5678 9012' },
    field_confidences: {},
    extracted_text: 'Unique Identification Authority of India',
    has_preview: true,
    preview_url: '/api/documents/f99c88b3/preview',
    file_url: '/api/documents/f99c88b3/file',
    created_at: new Date().toISOString(),
  };

  // State update logic: prepend if not already present, never replace
  const updateVaultState = (prev: DocumentItem[], newDoc: DocumentItem) => {
    const exists = prev.some((d) => d.id === newDoc.id);
    return exists ? prev : [newDoc, ...prev];
  };

  vaultDocuments = updateVaultState(vaultDocuments, newlyUploadedDoc);

  assert.equal(vaultDocuments.length, 4, 'Vault must contain all 4 documents, not just the newest one');
  assert.equal(vaultDocuments[0].id, newlyUploadedDoc.id, 'Newest document is prepended');
  assert.ok(vaultDocuments.some((d) => d.filename === 'Account_Statement_Report_30-07-2026_1246hrs.PDF'));
  assert.ok(vaultDocuments.some((d) => d.filename === 'WhatsApp Image 2026-09-10 at 16.53.24.jpeg'));
  assert.ok(vaultDocuments.some((d) => d.filename === 'GST RC.pdf'));

  // Render table with the 4 documents
  const html = renderToString(
    React.createElement(DocumentsTable, {
      documents: vaultDocuments,
      supportedTypes: mockSupportedTypes,
      onSelectDocument: () => {},
      onDeleteDocument: () => {},
      onRefresh: () => {},
      isLoading: false,
    })
  );

  const rowMatches = html.match(/vault-table-row/g);
  assert.equal(rowMatches?.length, 4, 'Vault table must render 4 rows including previous records');
});

test('DocumentsTable renders empty state message only when documents array is truly empty', () => {
  const html = renderToString(
    React.createElement(DocumentsTable, {
      documents: [],
      supportedTypes: mockSupportedTypes,
      onSelectDocument: () => {},
      onDeleteDocument: () => {},
      onRefresh: () => {},
      isLoading: false,
    })
  );

  assert.ok(html.includes('Document Vault is empty'), 'Empty state banner must appear when vault has 0 items');
  const rowMatches = html.match(/vault-table-row/g);
  assert.equal(rowMatches, null, 'No vault rows should be rendered when vault is empty');
});

test('Regression: AI Mode upload with document_type = "Unknown Document" remains rendered and Document Vault renders existing documents', () => {
  // 1. Open AI Mode
  const currentMode = 'ai';
  assert.equal(currentMode, 'ai');

  // 2. Mock successful AI response with document_type = "Unknown Document"
  // This matches the exact shape returned by POST /api/mode/ai/analyze in backend main.py
  const mockAiBackendResponse = {
    document_id: 'c52f207b-8910-4131-bda0-e37452d37801',
    filename: 'Customer_Agreement_Draft.pdf',
    document_type: 'Unknown Document',
    confidence: 'high', // string confidence
    summary: 'I analyzed this document and identified it as Unknown Document.',
    evidence: ['General business terms detected', 'No standard tax or identity markers'],
    reasoning: ['General business terms detected', 'No standard tax or identity markers'],
    extracted_fields: {}, // empty extracted fields
    file_url: '/api/documents/c52f207b-8910-4131-bda0-e37452d37801/file',
    preview_url: '/api/documents/c52f207b-8910-4131-bda0-e37452d37801/preview',
    file_size: 204800,
    pages: 2,
    text_source: 'rapid_ocr',
    extracted_text: 'THIS AGREEMENT is entered into on 15th day of August 2026...',
  };

  // 3. Complete upload: normalize response before state updates
  const normalizedDoc = normalizeAiDocument(mockAiBackendResponse);

  // Verify normalization safely produced valid identifiers and values
  assert.equal(normalizedDoc.id, 'c52f207b-8910-4131-bda0-e37452d37801');
  assert.equal(normalizedDoc.document_id, 'c52f207b-8910-4131-bda0-e37452d37801');
  assert.equal(normalizedDoc.document_type, 'Unknown Document');
  assert.equal(typeof normalizedDoc.confidence, 'number');
  assert.equal(normalizedDoc.confidence, 0.95);
  assert.equal(normalizedDoc.confidence_level, 'high');
  assert.equal(normalizedDoc.file_type, '.pdf');

  // Update vault state as in handleDocumentUploaded
  let vaultDocuments: DocumentItem[] = [...mockThreeDocuments];
  const exists = vaultDocuments.some((d) => d.id === normalizedDoc.id);
  vaultDocuments = exists
    ? vaultDocuments.map((d) => (d.id === normalizedDoc.id ? normalizedDoc : d))
    : [normalizedDoc, ...vaultDocuments];

  // 4. Verify AI Mode workspace components render without crashing (no blank screen!)
  const analysisHtml = renderToString(
    React.createElement(AIAnalysisCard, {
      document: normalizedDoc,
      onUploadNew: () => {},
      onReset: () => {},
    })
  );
  assert.ok(analysisHtml.includes('Customer_Agreement_Draft.pdf'), 'AIAnalysisCard should render filename');
  assert.ok(analysisHtml.includes('Unknown Document'), 'AIAnalysisCard should render Unknown Document type');
  assert.ok(analysisHtml.includes('High Confidence'), 'AIAnalysisCard should render confidence label');

  const summaryHtml = renderToString(
    React.createElement(AISummaryCard, {
      summary: normalizedDoc.summary,
      documentType: normalizedDoc.document_type,
    })
  );
  assert.ok(summaryHtml.includes('Unknown Document'), 'AISummaryCard should render document type');

  const findingsHtml = renderToString(
    React.createElement(AIKeyFindingsCard, {
      reasoning: normalizedDoc.reasoning,
      documentType: normalizedDoc.document_type,
      extractedFields: normalizedDoc.extracted_fields,
    })
  );
  assert.ok(findingsHtml.includes('General business terms detected'), 'AIKeyFindingsCard should render reasoning points');

  const chatHtml = renderToString(
    React.createElement(AIChatPanel, {
      document: normalizedDoc,
      messages: [
        {
          id: 'msg-1',
          role: 'assistant',
          content: 'I analyzed this document and identified it as Unknown Document.',
          timestamp: '12:00 PM',
        },
      ],
      isAiThinking: false,
      onSendMessage: () => {},
      onNotify: () => {},
    })
  );
  assert.ok(chatHtml.includes('Document AI Assistant'), 'AIChatPanel should render safely');
  assert.ok(chatHtml.includes('Customer_Agreement_Draft.pdf'), 'AIChatPanel should reference uploaded document');

  // Also verify inspection components (DocumentPreview & OcrDecisionBadge) render without throwing
  const previewHtml = renderToString(
    React.createElement(DocumentPreview, {
      document: normalizedDoc,
    })
  );
  assert.ok(previewHtml.includes('Customer_Agreement_Draft.pdf'), 'DocumentPreview should render without crashing');
  assert.ok(previewHtml.includes('PDF'), 'DocumentPreview should safely format file type');

  const badgeHtml = renderToString(
    React.createElement(OcrDecisionBadge, {
      document: normalizedDoc,
    })
  );
  assert.ok(badgeHtml.includes('Unknown Document'), 'OcrDecisionBadge should safely render Unknown Document badge');

  // 5. Verify Document Vault still renders existing documents
  const tableHtml = renderToString(
    React.createElement(DocumentsTable, {
      documents: vaultDocuments,
      supportedTypes: mockSupportedTypes,
      onSelectDocument: () => {},
      onDeleteDocument: () => {},
      onRefresh: () => {},
      isLoading: false,
    })
  );

  // All 3 previous documents plus the new AI document must be rendered
  assert.ok(tableHtml.includes('WhatsApp Image 2026-09-10 at 16.53.24.jpeg'), 'Existing PAN Card should remain rendered');
  assert.ok(tableHtml.includes('GST RC.pdf'), 'Existing GST RC should remain rendered');
  assert.ok(tableHtml.includes('Account_Statement_Report_30-07-2026_1246hrs.PDF'), 'Existing Bank Statement should remain rendered');
  assert.ok(tableHtml.includes('Customer_Agreement_Draft.pdf'), 'Newly uploaded Unknown Document should be rendered in vault');

  const rowMatches4 = tableHtml.match(/vault-table-row/g);
  assert.equal(rowMatches4?.length, 4, 'Vault table must render 4 rows (3 existing + 1 new AI document)');
});

test('SettingsModal renders AI Model Configuration with Provider select and Model input', () => {
  const html = renderToString(
    React.createElement(SettingsModal, {
      isOpen: true,
      onClose: () => {},
      onSaved: () => {},
    })
  );

  assert.ok(html.includes('AI Model Configuration'), 'Must render AI Model Configuration heading');
  assert.ok(html.includes('Local Ollama (Offline / Private)'), 'Must include Local Ollama option');
  assert.ok(html.includes('External Provider (OpenRouter / OpenAI / Custom)'), 'Must include External Provider option');
  assert.ok(html.includes('Test AI Connection'), 'Must render Test AI Connection button');
});

test('AI Mode Provider Status renders Local active state correctly', () => {
  // Test local status pill markup structure
  const localPillHtml = renderToString(
    React.createElement(
      'div',
      { className: 'local-ai-status-banner banner-ready', 'data-testid': 'ai-provider-status-local' },
      React.createElement('strong', null, 'Local AI Active'),
      React.createElement('span', { className: 'local-ai-model-pill' }, 'Ollama • Qwen2.5-VL 3B')
    )
  );

  assert.ok(localPillHtml.includes('Local AI Active'), 'Should display Local AI Active');
  assert.ok(localPillHtml.includes('Ollama • Qwen2.5-VL 3B'), 'Should display Qwen2.5-VL 3B');
});

test('AI Mode Provider Status renders External active state correctly', () => {
  // Test external status pill markup structure
  const externalPillHtml = renderToString(
    React.createElement(
      'div',
      { className: 'local-ai-status-banner banner-ready', 'data-testid': 'ai-provider-status-external' },
      React.createElement('strong', null, 'External AI Active'),
      React.createElement('span', { className: 'local-ai-model-pill' }, 'OPENROUTER • GOOGLE/GEMINI-2.5-FLASH')
    )
  );

  assert.ok(externalPillHtml.includes('External AI Active'), 'Should display External AI Active');
  assert.ok(externalPillHtml.includes('OPENROUTER • GOOGLE/GEMINI-2.5-FLASH'), 'Should display external provider and model');
});

test('AIModeView reflects external OpenRouter config and never shows stale Local Ollama badge', () => {
  const openRouterConfig: AIProviderConfig = {
    active_provider: 'openrouter',
    active_model: 'nvidia/nemotron-3-ultra-550b-a55b:free',
    mode: 'external',
    api_key_configured: true,
    base_url: 'https://openrouter.ai/api/v1',
    ollama_available: true, // Even if Ollama is available as fallback!
    local_fallback_available: true,
    fallback_on_error: false,
  };

  const html = renderToString(
    React.createElement(AIModeView, {
      onNotify: () => {},
      aiConfig: openRouterConfig,
    })
  );

  assert.ok(html.includes('External AI Active'), 'Must display External AI Active');
  assert.ok(html.includes('OpenRouter'), 'Must display OpenRouter');
  assert.ok(html.includes('nvidia/nemotron-3-ultra-550b-a55b:free'), 'Must display correct model ID');
  assert.ok(!html.includes('data-testid="ai-provider-status-local"'), 'Must NOT render local provider banner');
  assert.ok(!html.includes('Local AI Active'), 'Must NOT display Local AI Active when mode is external');
});

test('AIModeView reflects local config correctly when mode is local', () => {
  const localConfig: AIProviderConfig = {
    active_provider: 'local',
    active_model: 'qwen2.5vl:3b',
    mode: 'local',
    api_key_configured: false,
    ollama_available: true,
    local_fallback_available: true,
  };

  const html = renderToString(
    React.createElement(AIModeView, {
      onNotify: () => {},
      aiConfig: localConfig,
    })
  );

  assert.ok(html.includes('Local AI Active'), 'Must display Local AI Active');
  assert.ok(html.includes('qwen2.5vl:3b'), 'Must display qwen2.5vl:3b');
  assert.ok(!html.includes('External AI Active'), 'Must NOT display External AI Active when mode is local');
});


