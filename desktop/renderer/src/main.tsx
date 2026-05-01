import React from "react";
import ReactDOM from "react-dom/client";

import App from "./App";
import { SupabaseAuthProvider } from "./supabase/SupabaseAuthProvider";
import "./styles.css";

if (window.sabi && window.location.search.includes("sabiSmoke=1")) {
  document.body.dataset.sabiBridge = "available";
}

ReactDOM.createRoot(document.getElementById("root") as HTMLElement).render(
  <React.StrictMode>
    <SupabaseAuthProvider>
      <App />
    </SupabaseAuthProvider>
  </React.StrictMode>
);
