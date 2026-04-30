import type { Session } from "@supabase/supabase-js";
import { createContext } from "react";

export interface SupabaseAuthContextValue {
  configured: boolean;
  initializing: boolean;
  session: Session | null;
  signUp: (
    email: string,
    password: string
  ) => Promise<{ errorMessage: string | null; confirmationHint: boolean }>;
  signIn: (
    email: string,
    password: string
  ) => Promise<{ errorMessage: string | null }>;
  signOut: () => Promise<{ errorMessage: string | null }>;
}

export const SupabaseAuthContext = createContext<SupabaseAuthContextValue | null>(
  null
);
