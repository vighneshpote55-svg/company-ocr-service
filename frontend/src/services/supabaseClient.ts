/**
 * supabaseClient.ts
 * Browser Supabase Client for Authentication:
 * - Uses publishable anon key (safe for browser exposure)
 * - Persists session in browser according to standard Supabase Auth behavior
 * - NEVER exposes backend secret keys or API keys
 */

import { createClient, SupabaseClient } from '@supabase/supabase-js';

const supabaseUrl = import.meta.env.VITE_SUPABASE_URL || '';
const supabaseAnonKey = import.meta.env.VITE_SUPABASE_ANON_KEY || '';

export const isSupabaseConfigured = Boolean(supabaseUrl && supabaseAnonKey);

export const supabase: SupabaseClient = isSupabaseConfigured
  ? createClient(supabaseUrl, supabaseAnonKey, {
      auth: {
        persistSession: true,
        autoRefreshToken: true,
        detectSessionInUrl: true,
      },
    })
  : (null as unknown as SupabaseClient);

/**
 * Retrieve current JWT access token for FastAPI Bearer requests.
 */
export async function getAccessToken(): Promise<string | null> {
  if (!supabase) return null;
  try {
    const { data } = await supabase.auth.getSession();
    return data.session?.access_token || null;
  } catch {
    return null;
  }
}
