import { type FormEvent, useEffect, useState } from "react";

import { useSupabaseAuth } from "./supabase/useSupabaseAuth";
import { getSupabase } from "./supabaseClient";

export function SupabasePanel() {
  const { configured, initializing, session, signIn, signUp, signOut } = useSupabaseAuth();

  const [mode, setMode] = useState<"signin" | "signup">("signin");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [profilePreview, setProfilePreview] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    void (async () => {
      await Promise.resolve();
      const userId = session?.user?.id;
      if (!userId || !configured) {
        if (!cancelled) {
          setProfilePreview(null);
        }
        return;
      }

      try {
        const { data, error } = await getSupabase()
          .from("profiles")
          .select("display_name, updated_at, last_login_at")
          .eq("id", userId)
          .maybeSingle();

        if (cancelled) {
          return;
        }
        if (error) {
          const hintMissing =
            /relation|does not exist|schema cache/i.test(error.message) ||
            error.code === "PGRST116";
          setProfilePreview(
            hintMissing
              ? `Database: optional table profiles not found or not readable (${error.code ?? "hint"}). Add a profiles table + RLS in Supabase to sync row data here.`
              : `profiles: ${error.message}`
          );
          return;
        }
        if (!data) {
          setProfilePreview(
            "Signed in — no profile row yet. Insert into public.profiles(id) with your user id."
          );
          return;
        }
        const displayName =
          typeof data.display_name === "string" && data.display_name.trim()
            ? `Profile: ${data.display_name.trim()}`
            : "Profile row exists but display_name is empty — update it in Supabase.";
        const lastLogin =
          typeof data.last_login_at === "string"
            ? `Last login: ${formatTimestamp(data.last_login_at)}`
            : "Last login: not recorded yet.";
        const updated =
          typeof data.updated_at === "string"
            ? `Updated: ${formatTimestamp(data.updated_at)}`
            : null;

        setProfilePreview([displayName, lastLogin, updated].filter(Boolean).join(" | "));
      } catch {
        if (!cancelled) {
          setProfilePreview("profiles: unexpected error loading row.");
        }
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [configured, session]);

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setMessage(null);
    if (!password) {
      setMessage("Enter a password.");
      return;
    }
    setBusy(true);
    try {
      if (mode === "signup") {
        const { errorMessage, confirmationHint } = await signUp(email, password);
        if (errorMessage) {
          setMessage(errorMessage);
          return;
        }
        setMessage(
          confirmationHint
            ? "Account created — check email to confirm before signing in, if confirmations are enabled."
            : "Account created."
        );
        setPassword("");
        return;
      }
      const { errorMessage } = await signIn(email, password);
      if (errorMessage) {
        setMessage(errorMessage);
        return;
      }
      setPassword("");
      setMessage(null);
    } finally {
      setBusy(false);
    }
  }

  if (!configured) {
    return (
      <section className="settings-panel supabase-panel" aria-label="Account (Supabase)">
        <h2>Account</h2>
        <p className="muted">
          Supabase is not configured. Set <code>VITE_SUPABASE_URL</code> and{" "}
          <code>VITE_SUPABASE_PUBLISHABLE_KEY</code> in <code>desktop/.env</code> (see vite{" "}
          <code>envDir</code>).
        </p>
      </section>
    );
  }

  if (initializing) {
    return (
      <section className="settings-panel supabase-panel" aria-label="Account (Supabase)">
        <h2>Account</h2>
        <p className="muted">Restoring Supabase session…</p>
      </section>
    );
  }

  if (session?.user) {
    return (
      <section className="settings-panel supabase-panel" aria-label="Account (Supabase)">
        <h2>Account</h2>
        <p>{session.user.email ?? session.user.id}</p>
        {profilePreview ? <p className="muted">{profilePreview}</p> : null}
        <button
          type="button"
          disabled={busy}
          onClick={async () => {
            setBusy(true);
            setMessage(null);
            const result = await signOut();
            if (result.errorMessage) {
              setMessage(result.errorMessage);
            }
            setBusy(false);
          }}
        >
          Sign out
        </button>
        {message ? <p className="error">{message}</p> : null}
      </section>
    );
  }

  return (
    <section className="settings-panel supabase-panel" aria-label="Account (Supabase)">
      <h2>Account</h2>
      <div className="supabase-mode">
        <button
          type="button"
          className={mode === "signin" ? "active" : undefined}
          onClick={() => {
            setMode("signin");
            setMessage(null);
          }}
        >
          Sign in
        </button>
        <button
          type="button"
          className={mode === "signup" ? "active" : undefined}
          onClick={() => {
            setMode("signup");
            setMessage(null);
          }}
        >
          Create account
        </button>
      </div>
      <form className="supabase-form" onSubmit={(e) => void onSubmit(e)}>
        <label>
          Email
          <input
            autoComplete={mode === "signin" ? "email" : "email"}
            name="supabase-email"
            type="email"
            required
            value={email}
            onChange={(e) => setEmail(e.target.value)}
          />
        </label>
        <label>
          Password
          <input
            autoComplete={mode === "signin" ? "current-password" : "new-password"}
            name="supabase-password"
            type="password"
            required
            minLength={6}
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />
        </label>
        <button disabled={busy} type="submit">
          {busy ? "Working…" : mode === "signin" ? "Sign in" : "Sign up"}
        </button>
      </form>
      {message ? <p className="error">{message}</p> : null}
    </section>
  );
}

function formatTimestamp(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }

  return new Intl.DateTimeFormat(undefined, {
    dateStyle: "medium",
    timeStyle: "short"
  }).format(date);
}
