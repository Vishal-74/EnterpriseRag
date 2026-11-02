"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { FormEvent, useState } from "react";

import { api } from "@/lib/api";
import { ClientError } from "@/lib/types";

const LOCAL_EMAIL = "demo@example.com";
const LOCAL_PASSWORD = "review-pass-1";

export function AuthForm({ mode }: { mode: "login" | "register" }) {
  const router = useRouter();
  const params = useSearchParams();
  const [email, setEmail] = useState(mode === "login" ? LOCAL_EMAIL : "");
  const [password, setPassword] = useState(mode === "login" ? LOCAL_PASSWORD : "");
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    setError(null);
    setPending(true);
    try {
      if (mode === "login") {
        await api.login(email, password);
      } else {
        await api.register(email, password);
      }
      router.replace(params.get("next") || "/dashboard");
      router.refresh();
    } catch (caught) {
      setError(caught instanceof ClientError ? caught.message : "The request failed.");
    } finally {
      setPending(false);
    }
  }

  return (
    <main className="mx-auto flex min-h-screen max-w-md flex-col justify-center px-6">
      <p className="text-xs uppercase tracking-[0.2em] text-moss">Meridian</p>
      <h1 className="mt-3 font-display text-4xl">{mode === "login" ? "Sign in" : "Create an account"}</h1>
      <p className="mt-2 text-mist">
        {mode === "login" ? "Your library stays private to this account." : "Passwords are hashed before they are stored."}
      </p>
      <form className="mt-8 space-y-4" onSubmit={onSubmit}>
        <label className="block text-sm">
          Email
          <input
            className="mt-1 w-full rounded-xl border border-line bg-white px-3 py-2"
            type="email"
            name="email"
            autoComplete="username"
            required
            value={email}
            onChange={(event) => setEmail(event.target.value)}
          />
        </label>
        <label className="block text-sm">
          Password
          <input
            className="mt-1 w-full rounded-xl border border-line bg-white px-3 py-2"
            type="password"
            name="password"
            autoComplete={mode === "login" ? "current-password" : "new-password"}
            required
            minLength={mode === "register" ? 8 : 1}
            value={password}
            onChange={(event) => setPassword(event.target.value)}
          />
        </label>
        {error ? <p className="rounded-xl bg-red-50 px-3 py-2 text-sm text-red-800">{error}</p> : null}
        <button
          className="w-full rounded-full bg-ink px-4 py-2 text-paper disabled:opacity-60"
          disabled={pending}
          type="submit"
        >
          {pending ? "Working…" : mode === "login" ? "Sign in" : "Create account"}
        </button>
      </form>
      <p className="mt-6 text-sm text-mist">
        {mode === "login" ? (
          <Link className="underline" href="/register">
            Need an account?
          </Link>
        ) : (
          <Link className="underline" href="/login">
            Already registered?
          </Link>
        )}
      </p>
    </main>
  );
}
