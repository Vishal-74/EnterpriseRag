import { cookies } from "next/headers";

export const SESSION_COOKIE = "ei_session";

export function apiBaseUrl(): string {
  return process.env.API_URL || "http://localhost:8000";
}

export async function sessionToken(): Promise<string | undefined> {
  const jar = await cookies();
  return jar.get(SESSION_COOKIE)?.value;
}

export function cookieOptions() {
  return {
    httpOnly: true,
    sameSite: "lax" as const,
    secure: process.env.NODE_ENV === "production",
    path: "/",
    maxAge: 60 * 60,
  };
}
