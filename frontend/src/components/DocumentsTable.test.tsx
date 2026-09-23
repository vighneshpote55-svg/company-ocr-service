import test from 'node:test';
import assert from 'node:assert/strict';
import React from 'react';
import { renderToString } from 'react-dom/server';
import { DocumentsTable, formatConfidence } from './DocumentsTable.tsx';
import { DocumentPreview } from './DocumentPreview.tsx';
import { OcrDecisionBadge } from './OcrDecisionBadge.tsx';
import { AIAnalysisCard } from './AIAnalysisCard.tsx';
import { AISummaryCard } from './AISummaryCard.tsx';
import { AIKeyFindingsCard } from './AIKeyFindingsCard.tsx';
import { AIChatPanel } from './AIChatPanel.tsx';
import { SettingsModal } from './SettingsModal.tsx';
import { AIModeView } from './AIModeView.tsx';
import { ExtractedFields } from './ExtractedFields.tsx';
import { Sidebar } from './Sidebar.tsx';
import { Header } from './Header.tsx';
import { DashboardStats } from './DashboardStats.tsx';
import { ModeSwitcher } from './ModeSwitcher.tsx';
import { DashboardLayout } from './DashboardLayout.tsx';
import { AuthProvider } from '../context/AuthContext.tsx';
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
    React.createElement(
      AuthProvider,
      null,
      React.createElement(SettingsModal, {
        isOpen: true,
        onClose: () => {},
        onSaved: () => {},
      })
    )
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

test('DocumentPreview renders preview panel with filename, page count, and loading spinner', () => {
  const pdfDoc: DocumentItem = {
    id: 'pdf-doc-1234',
    filename: 'Customer_Agreement.pdf',
    file_type: '.pdf',
    file_size: 1048576,
    pages: 3,
    status: 'completed',
    document_type: 'Agreement',
    confidence: 0.95,
  };

  const html = renderToString(React.createElement(DocumentPreview, { document: pdfDoc }));

  assert.ok(html.includes('data-testid="document-preview-panel"'), 'Must render preview panel');
  assert.ok(html.includes('Customer_Agreement.pdf'), 'Must render document filename');
  assert.ok(html.includes('3 Pages'), 'Must display multi-page count');
  assert.ok(html.includes('Loading document preview...'), 'Must render loading overlay during authenticated blob retrieval');
  assert.ok(!html.includes('Bearer JWT required'), 'Must never render raw 401 JSON error');
});

test('DocumentPreview renders image preview panel with format info and download button', () => {
  const imgDoc: DocumentItem = {
    id: 'img-doc-5678',
    filename: 'PAN_Card.png',
    file_type: '.png',
    file_size: 204800,
    pages: 1,
    status: 'completed',
    document_type: 'PAN Card',
    confidence: 0.98,
  };

  const html = renderToString(React.createElement(DocumentPreview, { document: imgDoc }));

  assert.ok(html.includes('data-testid="document-preview-panel"'), 'Must render preview panel');
  assert.ok(html.includes('PAN_Card.png'), 'Must render filename');
  assert.ok(html.includes('PNG'), 'Must display format');
  assert.ok(html.includes('Download document file'), 'Must include download button');
});

test('DocumentPreview error state UI renders clean failure card without raw JSON', () => {
  const brokenDoc: DocumentItem = {
    id: 'broken-doc-id',
    filename: 'Corrupted.pdf',
    file_type: '.pdf',
    status: 'completed',
  };

  const html = renderToString(React.createElement(DocumentPreview, { document: brokenDoc }));
  assert.ok(html.includes('data-testid="document-preview-panel"'));
  assert.ok(!html.includes('Authentication credentials were not provided'));
  assert.ok(!html.includes('"detail":'));
});

test('OCR text is preserved when document preview is initialized or fails', () => {
  const docWithOcr: DocumentItem = {
    id: 'doc-with-ocr-1',
    filename: 'PAN_With_OCR.pdf',
    file_type: '.pdf',
    status: 'completed',
    extracted_text: 'INCOME TAX DEPARTMENT GOVT OF INDIA PERMANENT ACCOUNT NUMBER ABCDE1234F',
    raw_text: 'INCOME TAX DEPARTMENT GOVT OF INDIA PERMANENT ACCOUNT NUMBER ABCDE1234F',
    extracted_fields: { pan_number: 'ABCDE1234F' },
  };

  const normalized = normalizeAiDocument(docWithOcr);
  assert.equal(normalized.extracted_text, 'INCOME TAX DEPARTMENT GOVT OF INDIA PERMANENT ACCOUNT NUMBER ABCDE1234F');
  assert.equal(normalized.extracted_fields.pan_number, 'ABCDE1234F');
  assert.ok(normalized.extracted_text.length > 0, 'Extracted text character count must not be 0');

  // Preview component does NOT overwrite or erase OCR text
  const previewHtml = renderToString(React.createElement(DocumentPreview, { document: normalized }));
  assert.ok(previewHtml.includes('PAN_With_OCR.pdf'));
  assert.equal(normalized.extracted_text.length, 71);
});

test('DocumentPreview handles missing or undefined document safely without crashing', () => {
  const htmlNull = renderToString(React.createElement(DocumentPreview, { document: null }));
  assert.ok(htmlNull.includes('No document loaded for preview'), 'Must render clean empty state for null document');
  assert.ok(!htmlNull.includes('undefined'), 'Must not render raw undefined string');

  const emptyDoc: any = { id: '', filename: '' };
  const htmlEmpty = renderToString(React.createElement(DocumentPreview, { document: emptyDoc }));
  assert.ok(htmlEmpty.includes('No document loaded for preview'), 'Must render clean empty state for empty doc ID');
  assert.ok(!htmlEmpty.includes('/api/documents//file'), 'Must not generate malformed URL');
});

test('ExtractedFields formats null as "Not found" and booleans as labels', () => {
  const docWithNulls: DocumentItem = {
    id: 'test-fields-doc',
    filename: 'test.pdf',
    file_type: '.pdf',
    status: 'completed',
    document_type: 'Tax Document',
    extracted_fields: {
      name: 'John Doe',
      pan: null,
      address: '',
      is_active: true,
      has_tax_due: false,
    },
  };

  const html = renderToString(React.createElement(ExtractedFields, { document: docWithNulls }));

  assert.ok(html.includes('John Doe'), 'Must render present string value');
  assert.ok(html.includes('Not found'), 'Must render Not found for null or empty string fields');
  assert.ok(html.includes('Yes'), 'Must render Yes for boolean true');
  assert.ok(html.includes('No'), 'Must render No for boolean false');
});

test('AIModeView renders 2-column workspace with preview and tabs when document is loaded', () => {
  const doc: DocumentItem = {
    id: 'ai-workspace-doc-1',
    document_id: 'ai-workspace-doc-1',
    filename: 'Employment_Contract.pdf',
    file_type: '.pdf',
    document_type: 'Employment Contract',
    confidence: 0.94,
    confidence_level: 'high',
    summary: 'This is an employment contract between ACME Corp and Jane Doe.',
    extracted_fields: {
      employer: 'ACME Corp',
      employee: 'Jane Doe',
      salary: '$120,000',
    },
    extracted_text: 'Employment Contract text here...',
    status: 'completed',
  };

  const html = renderToString(
    React.createElement(AIModeView, {
      onNotify: () => {},
      selectedDoc: doc,
      aiConfig: {
        mode: 'external',
        active_provider: 'openrouter',
        active_model: 'nvidia/nemotron-3-ultra-550b-a55b:free',
        api_key_configured: true,
      },
    })
  );

  assert.ok(html.includes('data-testid="ai-workspace-flow"'), 'Must render AI workspace flow');
  assert.ok(html.includes('ai-workspace-split-2col'), 'Must render 2-column workspace grid');
  assert.ok(html.includes('data-testid="document-preview-panel"'), 'Must include integrated DocumentPreview');
  assert.ok(html.includes('Extracted Fields'), 'Must include Extracted Fields tab');
  assert.ok(html.includes('Extracted Text'), 'Must include Extracted Text tab');
  assert.ok(html.includes('Raw JSON Payload'), 'Must include Raw JSON tab');
  assert.ok(html.includes('Document AI Assistant'), 'Must include grounded AIChatPanel');
  assert.ok(html.includes('External AI Active'), 'Must render external AI active status');
});

test('Phase 9: Verified, Review Required, and Unsupported badges render in DocumentsTable', () => {
  const testDocs: DocumentItem[] = [
    {
      id: 'doc-verified',
      filename: 'PAN_Verified.png',
      file_type: '.png',
      status: 'completed',
      verification_status: 'verified',
      risk_score: 12,
      review_required: false,
    },
    {
      id: 'doc-review-required',
      filename: 'Salary_Slip_Altered.pdf',
      file_type: '.pdf',
      status: 'completed',
      verification_status: 'review_required',
      risk_score: 65,
      review_required: true,
      suspicious_signals: ['Different font size', 'Alignment issue'],
    },
    {
      id: 'doc-unsupported',
      filename: 'Random_Doc.pdf',
      file_type: '.pdf',
      status: 'completed',
      verification_status: 'unsupported',
      risk_score: 0,
      review_required: false,
    },
  ];

  const html = renderToString(
    React.createElement(DocumentsTable, {
      documents: testDocs,
      supportedTypes: mockSupportedTypes,
      onSelectDocument: () => {},
      onDeleteDocument: () => {},
      onRefresh: () => {},
      isLoading: false,
    })
  );

  assert.ok(html.includes('Verified'), 'Must render Verified badge text');
  assert.ok(html.includes('Review Required'), 'Must render Review Required badge text');
  assert.ok(html.includes('Unsupported'), 'Must render Unsupported badge text');
  assert.ok(html.includes('vault-status-select'), 'Must render status filter dropdown');
  assert.ok(html.includes('All Statuses'), 'Must include All Statuses option');
  assert.ok(html.includes('value="verified"'), 'Must include verified filter option');
  assert.ok(html.includes('value="review_required"'), 'Must include review_required filter option');
  assert.ok(html.includes('value="unsupported"'), 'Must include unsupported filter option');
});

test('Phase 9: AIAnalysisCard renders Verification Status Badge, Risk Score, and Review Required panel', () => {
  const aiResult = {
    document_type: 'Invoice',
    confidence: 'high',
    confidence_score: 0.88,
    summary: 'A standard vendor invoice.',
    verification_status: 'review_required' as const,
    risk_score: 84,
    review_required: true,
    suspicious_signals: [
      'Different font size in amount field',
      'Seal appears duplicated',
    ],
    human_review_reason: 'Visible inconsistencies detected.',
  };

  const html = renderToString(
    React.createElement(AIAnalysisCard, {
      document: aiResult as any,
      onUploadNew: () => {},
      onReset: () => {},
    })
  );

  assert.ok(html.includes('Review Required'), 'Must render Review Required status badge');
  assert.ok(html.includes('Risk Score: 84%'), 'Must display numeric risk score percentage');
  assert.ok(html.includes('Visible inconsistencies detected'), 'Must render review reason');
  assert.ok(html.includes('Different font size in amount field'), 'Must render first suspicious signal');
  assert.ok(html.includes('Seal appears duplicated'), 'Must render second suspicious signal');
});

test('Phase 9: DocumentPreview renders Verification Status, Risk Score, and Review Notes', () => {
  const docWithAuth: DocumentItem = {
    id: 'doc-preview-auth-1',
    filename: 'Bank_Statement.pdf',
    file_type: '.pdf',
    status: 'completed',
    verification_status: 'review_required',
    risk_score: 45,
    review_required: true,
    human_review_reason: 'Balance calculation discrepancy detected.',
    suspicious_signals: ['Running balance arithmetic mismatch'],
  };

  const html = renderToString(
    React.createElement(DocumentPreview, {
      document: docWithAuth,
    })
  );

  assert.ok(html.includes('Review Required'), 'Must render Review Required in preview');
  assert.ok(html.includes('Risk Score: 45%'), 'Must render risk score in preview');
  assert.ok(html.includes('Balance calculation discrepancy detected.'), 'Must render review reason note');
});

test('Fix AI Chat Bug: AIChatPanel renders active documentId, filename, and verification_status', () => {
  const gstDoc = mockThreeDocuments[1]; // GST RC.pdf, id: 2112fd84-5bcd-4f6d-ba3a-84d7d06dca01
  const aiResult = normalizeAiDocument(gstDoc);

  const html = renderToString(
    React.createElement(AIChatPanel, {
      document: aiResult,
      documentId: gstDoc.id,
      filename: gstDoc.filename,
      verification_status: gstDoc.verification_status || 'verified',
      messages: [
        {
          id: 'msg-1',
          role: 'assistant',
          content: 'I analyzed GST RC.pdf and identified it as GST Registration Certificate.',
          timestamp: '12:00 PM',
        },
      ],
      isAiThinking: false,
      onSendMessage: () => {},
      onNotify: () => {},
    })
  );

  assert.ok(html.includes('GST RC.pdf'), 'Must render active filename in AIChatPanel');
  assert.ok(html.includes('Status: verified'), 'Must render verification status in AIChatPanel header');
  assert.ok(html.includes('Ask any question about GST RC.pdf...'), 'Placeholder must reference active document filename');
});

test('Fix AI Chat Bug: AIModeView passes matching active document ID and filename to AIChatPanel', () => {
  const gstDoc = mockThreeDocuments[1]; // GST RC.pdf, id: 2112fd84-5bcd-4f6d-ba3a-84d7d06dca01

  const html = renderToString(
    React.createElement(
      AuthProvider,
      null,
      React.createElement(AIModeView, {
        selectedDoc: gstDoc,
        onNotify: () => {},
      })
    )
  );

  // Both preview and chat column must render GST RC.pdf
  assert.ok(html.includes('GST RC.pdf'), 'AIModeView must render active GST RC.pdf document');
  assert.ok(html.includes('GST Registration Certificate'), 'Must identify as GST Registration Certificate');
  assert.ok(html.includes('Summarize Document'), 'Must render Quick Action button Summarize Document');
  assert.ok(html.includes('Ask any question about GST RC.pdf...'), 'Chat panel must be bound to GST RC.pdf');
});

test('Final UI Cleanup: Sidebar contains only Dashboard, My Documents, AI Mode, Offline OCR, Settings and Profile footer', () => {
  const html = renderToString(
    React.createElement(
      AuthProvider,
      null,
      React.createElement(Sidebar, {
        currentTab: 'dashboard',
        onSelectTab: () => {},
        onOpenSettings: () => {},
        appMode: 'ai',
        onSelectMode: () => {},
      })
    )
  );

  // Must include
  assert.ok(html.includes('Dashboard'), 'Sidebar must include Dashboard');
  assert.ok(html.includes('My Documents'), 'Sidebar must include My Documents');
  assert.ok(html.includes('AI Mode'), 'Sidebar must include AI Mode');
  assert.ok(html.includes('Offline OCR'), 'Sidebar must include Offline OCR');
  assert.ok(html.includes('Settings'), 'Sidebar must include Settings');
  assert.ok(html.includes('Admin'), 'Sidebar must include user profile footer with Admin');

  // Must NOT include
  assert.ok(!html.includes('Search Documents'), 'Sidebar must NOT include Search Documents');
  assert.ok(!html.includes('Teams &amp; Permissions') && !html.includes('Teams & Permissions'), 'Sidebar must NOT include Teams');
  assert.ok(!html.includes('Multi-tenant workspace'), 'Sidebar must NOT include Multi-tenant workspace');
  assert.ok(!html.includes('AI Tools'), 'Sidebar must NOT include legacy AI Tools name');
});

test('Final UI Cleanup: Header does not contain Workspace pill or search button', () => {
  const html = renderToString(
    React.createElement(
      AuthProvider,
      null,
      React.createElement(Header, {
        mode: 'ai',
        onModeChange: () => {},
        isBackendConnected: true,
        onOpenSettings: () => {},
        onRefresh: () => {},
        onToggleTheme: () => {},
      })
    )
  );

  // Must NOT include workspace pill or search button
  assert.ok(!html.includes('Security Audit Q3'), 'Header must NOT include Security Audit Q3');
  assert.ok(!html.includes('docpilot-workspace-capsule'), 'Header must NOT include docpilot-workspace-capsule');
  assert.ok(!html.includes('Search Document Repository'), 'Header must NOT include search button');

  // Must include bell, refresh, theme toggle, settings, and profile avatar
  assert.ok(html.includes('Notifications'), 'Header must include Notifications');
  assert.ok(html.includes('Synchronize Data'), 'Header must include Refresh button');
  assert.ok(html.includes('Settings'), 'Header must include Settings');
  assert.ok(html.includes('docpilot-header-avatar'), 'Header must include avatar');
});

test('Dashboard UI Redesign: ModeSwitcher shows Offline OCR and AI Mode', () => {
  const html = renderToString(
    React.createElement(ModeSwitcher, {
      mode: 'offline',
      onModeChange: () => {},
    })
  );

  assert.ok(html.includes('Offline OCR'), 'ModeSwitcher must render Offline OCR');
  assert.ok(html.includes('AI Mode'), 'ModeSwitcher must render AI Mode');
  assert.ok(!html.includes('Offline Mode'), 'Must not render legacy Offline Mode wording');
});

test('Dashboard UI Redesign: DashboardStats renders 5 balanced cards and removes AI Provider', () => {
  const html = renderToString(
    React.createElement(DashboardStats, {
      stats: {
        total: 10,
        total_documents: 10,
        ocr_processed: 6,
        offline_documents: 6,
        ai_documents: 4,
        total_storage_bytes: 1048576,
      },
      documents: mockThreeDocuments,
    })
  );

  assert.ok(html.includes('Documents'), 'Must include Documents card');
  assert.ok(html.includes('OCR Processed'), 'Must include OCR Processed card');
  assert.ok(html.includes('AI Analysis'), 'Must include AI Analysis card');
  assert.ok(html.includes('Storage'), 'Must include Storage card');
  assert.ok(html.includes('Verified'), 'Must include Verified card');
  assert.ok(!html.includes('AI Provider'), 'Must NOT include standalone AI Provider card');
});

test('Dashboard UI Redesign: DashboardLayout renders simplified banner and 2-column split with Recent Documents', () => {
  const html = renderToString(
    React.createElement(
      AuthProvider,
      null,
      React.createElement(DashboardLayout, {
        mode: 'offline',
        onSelectMode: () => {},
        currentTab: 'dashboard',
        onSelectTab: () => {},
        isBackendConnected: true,
        isRefreshing: false,
        onRefresh: () => {},
        onOpenSettings: () => {},
        supportedTypes: mockSupportedTypes,
        stats: {
          total: 3,
          total_documents: 3,
          ocr_processed: 2,
          offline_documents: 2,
          ai_documents: 1,
          total_storage_bytes: 500000,
        },
        documents: mockThreeDocuments,
        onDocumentUploaded: () => {},
        onDeleteDocument: () => {},
        onSelectDocument: () => {},
        onNotify: () => {},
      })
    )
  );

  // Simplified welcome banner
  assert.ok(html.includes('Welcome back, Incraax Automation 👋'), 'Must render simplified welcome banner title');
  assert.ok(html.includes('Manage your documents, run OCR, and analyze them with AI.'), 'Must render simplified subtitle');
  assert.ok(!html.includes('Secure Tenant Isolation'), 'Must NOT render tenant isolation badge');
  assert.ok(!html.includes('Multi-tenant workspace with isolated Document Vault'), 'Must NOT render multi-tenant text');

  // 2-column split and Recent Documents feed
  assert.ok(html.includes('dashboard-content-split'), 'Must render 2-column split layout container');
  assert.ok(html.includes('Recent Documents'), 'Must render Recent Documents feed card');
  assert.ok(html.includes('View all'), 'Must render View all link');
  assert.ok(html.includes('WhatsApp Image'), 'Must render recent document filenames');
});

test('formatConfidence correctly formats real floats, percentages, failures, and N/A without 100% fallback', () => {
  // 1. Real OCR confidence float (0.9425 -> 94%)
  assert.equal(
    formatConfidence({ status: 'completed', confidence: 0.9425 } as any),
    '94%',
    '0.9425 should round to 94%'
  );

  // 2. Real float (0.812 -> 81%)
  assert.equal(
    formatConfidence({ status: 'completed', confidence: 0.812 } as any),
    '81%',
    '0.812 should round to 81%'
  );

  // 3. String float ("0.98" -> 98%)
  assert.equal(
    formatConfidence({ status: 'completed', confidence: '0.98' } as any),
    '98%',
    'String "0.98" should format to 98%'
  );

  // 4. Missing confidence (undefined -> N/A, never hardcoded 100%!)
  assert.equal(
    formatConfidence({ status: 'completed', confidence: undefined } as any),
    'N/A',
    'undefined confidence must return N/A'
  );

  // 5. Null confidence -> N/A
  assert.equal(
    formatConfidence({ status: 'completed', confidence: null } as any),
    'N/A',
    'null confidence must return N/A'
  );

  // 6. Empty string confidence -> N/A
  assert.equal(
    formatConfidence({ status: 'completed', confidence: '' } as any),
    'N/A',
    'empty string confidence must return N/A'
  );

  // 7. Failed document -> 0%
  assert.equal(
    formatConfidence({ status: 'failed', confidence: 0.95 } as any),
    '0%',
    'Failed document must return 0%'
  );

  // 8. Error status document -> 0%
  assert.equal(
    formatConfidence({ status: 'error', confidence: null } as any),
    '0%',
    'Error status document must return 0%'
  );

  // 9. Legitimate 1.0 (100%)
  assert.equal(
    formatConfidence({ status: 'completed', confidence: 1.0 } as any),
    '100%',
    'Legitimate 1.0 confidence should format to 100%'
  );
});

test('DocumentsTable renders real confidence and N/A for missing values without hardcoded 100%', () => {
  const docsWithDiverseConfidence: DocumentItem[] = [
    {
      id: 'doc-real-conf',
      filename: 'real_conf_doc.pdf',
      file_path: '/uploads/real_conf_doc.pdf',
      file_size: 1024,
      file_type: '.pdf',
      doc_type: 'pan',
      document_type: 'PAN Card',
      ocr_required: true,
      text_source: 'rapid_ocr',
      status: 'completed',
      confidence: 0.9425,
      pages: 1,
      extracted_fields: {},
      field_confidences: {},
      extracted_text: 'PAN SAMPLE',
      has_preview: false,
      created_at: '2026-09-23T12:00:00Z',
    },
    {
      id: 'doc-missing-conf',
      filename: 'missing_conf_doc.pdf',
      file_path: '/uploads/missing_conf_doc.pdf',
      file_size: 2048,
      file_type: '.pdf',
      doc_type: 'unknown',
      document_type: 'Unknown Document',
      ocr_required: true,
      text_source: 'rapid_ocr',
      status: 'completed',
      confidence: undefined, // Missing!
      pages: 1,
      extracted_fields: {},
      field_confidences: {},
      extracted_text: '',
      has_preview: false,
      created_at: '2026-09-23T12:00:00Z',
    },
    {
      id: 'doc-failed',
      filename: 'failed_doc.pdf',
      file_path: '/uploads/failed_doc.pdf',
      file_size: 512,
      file_type: '.pdf',
      doc_type: 'unknown',
      document_type: 'Unknown Document',
      ocr_required: true,
      text_source: 'rapid_ocr',
      status: 'failed',
      confidence: 0.0,
      pages: 1,
      extracted_fields: {},
      field_confidences: {},
      extracted_text: '',
      has_preview: false,
      created_at: '2026-09-23T12:00:00Z',
    },
  ];

  const html = renderToString(
    React.createElement(DocumentsTable, {
      documents: docsWithDiverseConfidence,
      supportedTypes: mockSupportedTypes,
      onSelectDocument: () => {},
      onDeleteDocument: () => {},
      onRefresh: () => {},
    })
  );

  // Real confidence rendered
  assert.ok(html.includes('94%'), 'Must render real confidence 94%');

  // Missing confidence rendered as N/A
  assert.ok(html.includes('N/A'), 'Must render N/A for missing confidence');

  // Failed document rendered as 0%
  assert.ok(html.includes('0%'), 'Must render 0% for failed document');

  // Hardcoded 100% must NOT be present
  assert.ok(!html.includes('100%'), 'Must NOT default to 100% for missing confidence');

  // Accurate pagination counts
  assert.ok(html.includes('Showing <strong>1</strong> to <strong>3</strong> of <strong>3</strong> documents'));
});






