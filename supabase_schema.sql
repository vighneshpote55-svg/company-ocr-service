-- ==============================================================================
-- Company OCR Service - Supabase PostgreSQL Schema & RLS Policies
-- ==============================================================================

-- 1. Profiles Table (extends auth.users)
CREATE TABLE IF NOT EXISTS public.profiles (
    id UUID PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
    email TEXT NOT NULL,
    full_name TEXT,
    role TEXT NOT NULL DEFAULT 'user' CHECK (role IN ('user', 'admin')),
    avatar_url TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Index on email for fast lookups
CREATE INDEX IF NOT EXISTS idx_profiles_email ON public.profiles(email);

-- Trigger to create/update public.profiles when auth.users is created
CREATE OR REPLACE FUNCTION public.handle_new_user()
RETURNS TRIGGER AS $$
BEGIN
    INSERT INTO public.profiles (id, email, full_name, role)
    VALUES (
        NEW.id,
        NEW.email,
        COALESCE(NEW.raw_user_meta_data->>'full_name', ''),
        COALESCE(NEW.raw_user_meta_data->>'role', 'user')
    )
    ON CONFLICT (id) DO UPDATE
    SET email = EXCLUDED.email,
        full_name = CASE WHEN EXCLUDED.full_name <> '' THEN EXCLUDED.full_name ELSE public.profiles.full_name END,
        updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

DROP TRIGGER IF EXISTS on_auth_user_created ON auth.users;
CREATE TRIGGER on_auth_user_created
    AFTER INSERT OR UPDATE ON auth.users
    FOR EACH ROW EXECUTE FUNCTION public.handle_new_user();


-- 2. Documents Table (user-owned documents)
CREATE TABLE IF NOT EXISTS public.documents (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    original_filename TEXT NOT NULL,
    file_type TEXT NOT NULL,
    storage_path TEXT NOT NULL,
    doc_type TEXT,
    mode TEXT NOT NULL DEFAULT 'offline' CHECK (mode IN ('offline', 'ai')),
    status TEXT NOT NULL DEFAULT 'uploaded',
    file_size BIGINT,
    checksum_sha256 TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_documents_user_id ON public.documents(user_id);
CREATE INDEX IF NOT EXISTS idx_documents_created_at ON public.documents(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_documents_status ON public.documents(status);


-- 3. Document Files Table (metadata for encrypted stored objects)
CREATE TABLE IF NOT EXISTS public.document_files (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id UUID NOT NULL REFERENCES public.documents(id) ON DELETE CASCADE,
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    bucket_name TEXT NOT NULL DEFAULT 'company-documents',
    storage_path TEXT NOT NULL,
    encryption_algorithm TEXT NOT NULL DEFAULT 'AES-256-GCM',
    file_size BIGINT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_document_files_document_id ON public.document_files(document_id);
CREATE INDEX IF NOT EXISTS idx_document_files_user_id ON public.document_files(user_id);


-- 4. OCR Results Table
CREATE TABLE IF NOT EXISTS public.ocr_results (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id UUID NOT NULL REFERENCES public.documents(id) ON DELETE CASCADE,
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    raw_text TEXT,
    detected_type TEXT,
    confidence NUMERIC(5, 2),
    page_count INTEGER DEFAULT 1,
    raw_results JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_ocr_results_document_id ON public.ocr_results(document_id);
CREATE INDEX IF NOT EXISTS idx_ocr_results_user_id ON public.ocr_results(user_id);


-- 5. Extracted Fields Table
CREATE TABLE IF NOT EXISTS public.extracted_fields (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id UUID NOT NULL REFERENCES public.documents(id) ON DELETE CASCADE,
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    fields JSONB NOT NULL DEFAULT '{}'::jsonb,
    verification_status TEXT DEFAULT 'pending',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_extracted_fields_document_id ON public.extracted_fields(document_id);
CREATE INDEX IF NOT EXISTS idx_extracted_fields_user_id ON public.extracted_fields(user_id);


-- 6. AI Analyses Table
CREATE TABLE IF NOT EXISTS public.ai_analyses (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id UUID NOT NULL REFERENCES public.documents(id) ON DELETE CASCADE,
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    provider TEXT NOT NULL,
    model TEXT NOT NULL,
    summary TEXT,
    classification TEXT,
    raw_analysis JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_ai_analyses_document_id ON public.ai_analyses(document_id);
CREATE INDEX IF NOT EXISTS idx_ai_analyses_user_id ON public.ai_analyses(user_id);


-- 7. Chat Sessions & Messages Tables
CREATE TABLE IF NOT EXISTS public.chat_sessions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id UUID NOT NULL REFERENCES public.documents(id) ON DELETE CASCADE,
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    provider TEXT NOT NULL,
    model TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_chat_sessions_doc_user ON public.chat_sessions(document_id, user_id);

CREATE TABLE IF NOT EXISTS public.chat_messages (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id UUID NOT NULL REFERENCES public.chat_sessions(id) ON DELETE CASCADE,
    document_id UUID NOT NULL REFERENCES public.documents(id) ON DELETE CASCADE,
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    role TEXT NOT NULL CHECK (role IN ('user', 'assistant', 'system')),
    content TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_chat_messages_session_id ON public.chat_messages(session_id);
CREATE INDEX IF NOT EXISTS idx_chat_messages_doc_user ON public.chat_messages(document_id, user_id);


-- 8. Global AI Provider Configs Table (managed by Admin)
CREATE TABLE IF NOT EXISTS public.ai_provider_configs (
    id TEXT PRIMARY KEY DEFAULT 'global',
    active_provider TEXT NOT NULL DEFAULT 'local',
    active_model TEXT NOT NULL DEFAULT 'qwen2.5vl:3b',
    mode TEXT NOT NULL DEFAULT 'local',
    base_url TEXT,
    encrypted_api_key TEXT,
    fallback_on_error BOOLEAN NOT NULL DEFAULT false,
    updated_by UUID REFERENCES auth.users(id),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);


-- ==============================================================================
-- ROW LEVEL SECURITY (RLS) POLICIES
-- ==============================================================================

-- Enable RLS across all tables
ALTER TABLE public.profiles ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.documents ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.document_files ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.ocr_results ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.extracted_fields ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.ai_analyses ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.chat_sessions ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.chat_messages ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.ai_provider_configs ENABLE ROW LEVEL SECURITY;

-- Profiles: Users can view and update their own profile
DROP POLICY IF EXISTS "Users can view own profile" ON public.profiles;
CREATE POLICY "Users can view own profile" ON public.profiles
    FOR SELECT USING (auth.uid() = id);

DROP POLICY IF EXISTS "Users can update own profile" ON public.profiles;
CREATE POLICY "Users can update own profile" ON public.profiles
    FOR UPDATE USING (auth.uid() = id);

-- Documents: Users have full CRUD over their own documents
DROP POLICY IF EXISTS "Users can view own documents" ON public.documents;
CREATE POLICY "Users can view own documents" ON public.documents
    FOR SELECT USING (auth.uid() = user_id);

DROP POLICY IF EXISTS "Users can insert own documents" ON public.documents;
CREATE POLICY "Users can insert own documents" ON public.documents
    FOR INSERT WITH CHECK (auth.uid() = user_id);

DROP POLICY IF EXISTS "Users can update own documents" ON public.documents;
CREATE POLICY "Users can update own documents" ON public.documents
    FOR UPDATE USING (auth.uid() = user_id);

DROP POLICY IF EXISTS "Users can delete own documents" ON public.documents;
CREATE POLICY "Users can delete own documents" ON public.documents
    FOR DELETE USING (auth.uid() = user_id);

-- Document Files
DROP POLICY IF EXISTS "Users can view own document files" ON public.document_files;
CREATE POLICY "Users can view own document files" ON public.document_files
    FOR SELECT USING (auth.uid() = user_id);

DROP POLICY IF EXISTS "Users can insert own document files" ON public.document_files;
CREATE POLICY "Users can insert own document files" ON public.document_files
    FOR INSERT WITH CHECK (auth.uid() = user_id);

DROP POLICY IF EXISTS "Users can delete own document files" ON public.document_files;
CREATE POLICY "Users can delete own document files" ON public.document_files
    FOR DELETE USING (auth.uid() = user_id);

-- OCR Results
DROP POLICY IF EXISTS "Users can view own OCR results" ON public.ocr_results;
CREATE POLICY "Users can view own OCR results" ON public.ocr_results
    FOR SELECT USING (auth.uid() = user_id);

DROP POLICY IF EXISTS "Users can insert own OCR results" ON public.ocr_results;
CREATE POLICY "Users can insert own OCR results" ON public.ocr_results
    FOR INSERT WITH CHECK (auth.uid() = user_id);

DROP POLICY IF EXISTS "Users can delete own OCR results" ON public.ocr_results;
CREATE POLICY "Users can delete own OCR results" ON public.ocr_results
    FOR DELETE USING (auth.uid() = user_id);

-- Extracted Fields
DROP POLICY IF EXISTS "Users can view own extracted fields" ON public.extracted_fields;
CREATE POLICY "Users can view own extracted fields" ON public.extracted_fields
    FOR SELECT USING (auth.uid() = user_id);

DROP POLICY IF EXISTS "Users can insert own extracted fields" ON public.extracted_fields;
CREATE POLICY "Users can insert own extracted fields" ON public.extracted_fields
    FOR INSERT WITH CHECK (auth.uid() = user_id);

DROP POLICY IF EXISTS "Users can delete own extracted fields" ON public.extracted_fields;
CREATE POLICY "Users can delete own extracted fields" ON public.extracted_fields
    FOR DELETE USING (auth.uid() = user_id);

-- AI Analyses
DROP POLICY IF EXISTS "Users can view own AI analyses" ON public.ai_analyses;
CREATE POLICY "Users can view own AI analyses" ON public.ai_analyses
    FOR SELECT USING (auth.uid() = user_id);

DROP POLICY IF EXISTS "Users can insert own AI analyses" ON public.ai_analyses;
CREATE POLICY "Users can insert own AI analyses" ON public.ai_analyses
    FOR INSERT WITH CHECK (auth.uid() = user_id);

DROP POLICY IF EXISTS "Users can delete own AI analyses" ON public.ai_analyses;
CREATE POLICY "Users can delete own AI analyses" ON public.ai_analyses
    FOR DELETE USING (auth.uid() = user_id);

-- Chat Sessions & Messages
DROP POLICY IF EXISTS "Users can view own chat sessions" ON public.chat_sessions;
CREATE POLICY "Users can view own chat sessions" ON public.chat_sessions
    FOR SELECT USING (auth.uid() = user_id);

DROP POLICY IF EXISTS "Users can insert own chat sessions" ON public.chat_sessions;
CREATE POLICY "Users can insert own chat sessions" ON public.chat_sessions
    FOR INSERT WITH CHECK (auth.uid() = user_id);

DROP POLICY IF EXISTS "Users can delete own chat sessions" ON public.chat_sessions;
CREATE POLICY "Users can delete own chat sessions" ON public.chat_sessions
    FOR DELETE USING (auth.uid() = user_id);

DROP POLICY IF EXISTS "Users can view own chat messages" ON public.chat_messages;
CREATE POLICY "Users can view own chat messages" ON public.chat_messages
    FOR SELECT USING (auth.uid() = user_id);

DROP POLICY IF EXISTS "Users can insert own chat messages" ON public.chat_messages;
CREATE POLICY "Users can insert own chat messages" ON public.chat_messages
    FOR INSERT WITH CHECK (auth.uid() = user_id);

DROP POLICY IF EXISTS "Users can delete own chat messages" ON public.chat_messages;
CREATE POLICY "Users can delete own chat messages" ON public.chat_messages
    FOR DELETE USING (auth.uid() = user_id);

-- AI Provider Configs: Any authenticated user can view (safe read), only admins can modify
DROP POLICY IF EXISTS "Authenticated users can view AI config" ON public.ai_provider_configs;
CREATE POLICY "Authenticated users can view AI config" ON public.ai_provider_configs
    FOR SELECT TO authenticated USING (true);

DROP POLICY IF EXISTS "Admins can update AI config" ON public.ai_provider_configs;
CREATE POLICY "Admins can update AI config" ON public.ai_provider_configs
    FOR ALL TO authenticated
    USING (
        EXISTS (
            SELECT 1 FROM public.profiles
            WHERE profiles.id = auth.uid() AND profiles.role = 'admin'
        )
    );

-- ==============================================================================
-- STORAGE BUCKET CONFIGURATION (Note: can also be executed via dashboard)
-- ==============================================================================
INSERT INTO storage.buckets (id, name, public)
VALUES ('company-documents', 'company-documents', false)
ON CONFLICT (id) DO UPDATE SET public = false;

-- Storage RLS: Users can only upload and read files in their own user directory: documents/<user_id>/*
DROP POLICY IF EXISTS "User Storage Read Policy" ON storage.objects;
CREATE POLICY "User Storage Read Policy" ON storage.objects
    FOR SELECT TO authenticated
    USING (bucket_id = 'company-documents' AND (storage.foldername(name))[2] = auth.uid()::text);

DROP POLICY IF EXISTS "User Storage Insert Policy" ON storage.objects;
CREATE POLICY "User Storage Insert Policy" ON storage.objects
    FOR INSERT TO authenticated
    WITH CHECK (bucket_id = 'company-documents' AND (storage.foldername(name))[2] = auth.uid()::text);

DROP POLICY IF EXISTS "User Storage Delete Policy" ON storage.objects;
CREATE POLICY "User Storage Delete Policy" ON storage.objects
    FOR DELETE TO authenticated
    USING (bucket_id = 'company-documents' AND (storage.foldername(name))[2] = auth.uid()::text);
