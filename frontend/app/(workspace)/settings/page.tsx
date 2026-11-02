"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";

import { api } from "@/lib/api";

export default function SettingsPage() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [provider, setProvider] = useState("openai");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api
      .me()
      .then((user) => setEmail(user.email))
      .catch((caught: Error) => setError(caught.message));
    const stored = window.localStorage.getItem("meridian-provider");
    if (stored === "openai" || stored === "anthropic") setProvider(stored);
  }, []);

  async function logout() {
    await api.logout();
    router.replace("/login");
    router.refresh();
  }

  return (
    <div className="max-w-xl space-y-6">
      <h1 className="font-display text-4xl">Settings</h1>
      {error ? <p className="text-red-800">{error}</p> : null}
      <p>
        Signed in as <span className="font-medium">{email || "…"}</span>
      </p>
      <label className="block text-sm">
        Default model for new questions
        <select
          className="mt-1 block rounded-lg border border-line bg-white px-3 py-2"
          value={provider}
          onChange={(event) => {
            setProvider(event.target.value);
            window.localStorage.setItem("meridian-provider", event.target.value);
          }}
        >
          <option value="openai">OpenAI</option>
          <option value="anthropic">Claude</option>
        </select>
      </label>
      <p className="text-sm text-mist">
        The session token stays in an httpOnly cookie on this site. The model preference is only a UI default.
      </p>
      <button className="rounded-full bg-ink px-4 py-2 text-paper" type="button" onClick={() => void logout()}>
        Log out
      </button>
    </div>
  );
}
