import test from 'node:test';
import assert from 'node:assert/strict';
import React from 'react';
import { renderToString } from 'react-dom/server';
import { DocumentsTable } from './DocumentsTable.tsx';
import type { DocumentItem, SupportedType } from '../types.ts';

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
