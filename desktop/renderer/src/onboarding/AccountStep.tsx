import { type FormEvent, useState } from "react";

import { useSupabaseAuth } from "../supabase/useSupabaseAuth";
import type { StepProps } from "./types";

export function AccountStep({ goTo }: StepProps) {
  const { configured, initializing, session, signIn, signUp } = useSupabaseAuth();
  const [mode, setMode] = useState<"signin" | "signup">("signup");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

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
            ? "Account created. Check your email to confirm it, then sign in to continue."
            : "Account created. Continue once your session is ready."
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
      <div className="wizard-step">
        <h2>Create your Sabi account</h2>
        <p>
          Supabase is not configured. Set <code>VITE_SUPABASE_URL</code> and{" "}
          <code>VITE_SUPABASE_PUBLISHABLE_KEY</code> in <code>desktop/.env</code> before
          continuing.
        </p>
      </div>
    );
  }

  if (initializing) {
    return (
      <div className="wizard-step">
        <h2>Create your Sabi account</h2>
        <p>Restoring your account session...</p>
      </div>
    );
  }

  if (session?.user) {
    return (
      <div className="wizard-step">
        <h2>Account ready</h2>
        <p>Signed in as {session.user.email ?? session.user.id}.</p>
        <button type="button" onClick={() => void goTo("profile")}>
          Continue
        </button>
      </div>
    );
  }

  return (
    <div className="wizard-step">
      <h2>Create your Sabi account</h2>
      <p>Sign up or sign in before continuing to profile setup and permissions.</p>
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
      <form className="supabase-form" onSubmit={(event) => void onSubmit(event)}>
        <label>
          Email
          <input
            autoComplete="email"
            name="onboarding-email"
            type="email"
            required
            value={email}
            onChange={(event) => setEmail(event.target.value)}
          />
        </label>
        <label>
          Password
          <input
            autoComplete={mode === "signin" ? "current-password" : "new-password"}
            name="onboarding-password"
            type="password"
            required
            minLength={6}
            value={password}
            onChange={(event) => setPassword(event.target.value)}
          />
        </label>
        <button disabled={busy} type="submit">
          {busy ? "Working..." : mode === "signin" ? "Sign in" : "Sign up"}
        </button>
      </form>
      {message ? <p className="error">{message}</p> : null}
    </div>
  );
}
