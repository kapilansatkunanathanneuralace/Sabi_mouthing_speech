import { createClient, type SupabaseClient } from "@supabase/supabase-js";

const url = import.meta.env.VITE_SUPABASE_URL ?? "";
const key =
  import.meta.env.VITE_SUPABASE_PUBLISHABLE_KEY ?? import.meta.env.VITE_SUPABASE_ANON_KEY ?? "";

export function isSupabaseConfigured(): boolean {
  return Boolean(url.trim() && key.trim());
}

let singleton: SupabaseClient | null = null;

export function getSupabase(): SupabaseClient {
  if (!isSupabaseConfigured()) {
    throw new Error("Supabase URL or publishable key is missing.");
  }
  singleton ??= createClient(url, key, {
    auth: {
      persistSession: true,
      autoRefreshToken: true
    }
  });
  return singleton;
}
