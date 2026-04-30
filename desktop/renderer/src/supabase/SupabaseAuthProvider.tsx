import type { Session } from "@supabase/supabase-js";
import {
  useCallback,
  useEffect,
  useMemo,
  useState,
  type ReactNode
} from "react";

import { SupabaseAuthContext, type SupabaseAuthContextValue } from "./SupabaseAuthContext";
import { getSupabase, isSupabaseConfigured } from "../supabaseClient";

export function SupabaseAuthProvider({ children }: { children: ReactNode }) {
  const configured = isSupabaseConfigured();

  const [session, setSession] = useState<Session | null>(null);

  const [initializing, setInitializing] = useState(() => configured);

  useEffect(() => {
    let alive = true;
    let unsubscribe: (() => void) | undefined;

    void (async () => {
      await Promise.resolve();
      if (!alive) {
        return;
      }

      if (!configured) {
        setSession(null);
        setInitializing(false);
        return;
      }

      const client = getSupabase();

      const {
        data: { session: initialSession },
        error
      } = await client.auth.getSession();

      if (!alive) {
        return;
      }

      setSession(error ? null : initialSession);
      setInitializing(false);

      const {
        data: { subscription }
      } = client.auth.onAuthStateChange((_event, next) => {
        setSession(next);
      });

      if (!alive) {
        subscription.unsubscribe();
        return;
      }

      unsubscribe = () => subscription.unsubscribe();
    })();

    return () => {
      alive = false;
      unsubscribe?.();
    };
  }, [configured]);

  const signUp = useCallback(async (email: string, password: string) => {
    if (!configured) {
      return { errorMessage: "Supabase is not configured.", confirmationHint: false };
    }
    try {
      const client = getSupabase();
      const trimmed = email.trim();
      const { error, data } = await client.auth.signUp({ email: trimmed, password });
      if (error) {
        return { errorMessage: error.message, confirmationHint: false };
      }
      const needsConfirm = Boolean(data.user) && data.session === null;
      return {
        errorMessage: null as string | null,
        confirmationHint: needsConfirm
      };
    } catch (err) {
      return {
        errorMessage: err instanceof Error ? err.message : String(err),
        confirmationHint: false
      };
    }
  }, [configured]);

  const signIn = useCallback(async (email: string, password: string) => {
    if (!configured) {
      return { errorMessage: "Supabase is not configured." };
    }
    try {
      const client = getSupabase();
      const trimmed = email.trim();
      const { error } = await client.auth.signInWithPassword({ email: trimmed, password });
      if (error) {
        return { errorMessage: error.message };
      }
      return { errorMessage: null as string | null };
    } catch (err) {
      return {
        errorMessage: err instanceof Error ? err.message : String(err)
      };
    }
  }, [configured]);

  const signOut = useCallback(async () => {
    if (!configured) {
      return { errorMessage: "Supabase is not configured." };
    }
    try {
      const { error } = await getSupabase().auth.signOut();
      if (error) {
        return { errorMessage: error.message };
      }
      return { errorMessage: null as string | null };
    } catch (err) {
      return {
        errorMessage: err instanceof Error ? err.message : String(err)
      };
    }
  }, [configured]);

  const value = useMemo(
    (): SupabaseAuthContextValue => ({
      configured,
      initializing,
      session,
      signUp,
      signIn,
      signOut
    }),
    [configured, initializing, session, signIn, signOut, signUp]
  );

  return <SupabaseAuthContext.Provider value={value}>{children}</SupabaseAuthContext.Provider>;
}
