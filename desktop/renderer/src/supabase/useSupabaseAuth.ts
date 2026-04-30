import { useContext } from "react";

import { SupabaseAuthContext, type SupabaseAuthContextValue } from "./SupabaseAuthContext";

export function useSupabaseAuth(): SupabaseAuthContextValue {
  const ctx = useContext(SupabaseAuthContext);
  if (!ctx) {
    throw new Error("useSupabaseAuth must be used inside SupabaseAuthProvider.");
  }
  return ctx;
}
