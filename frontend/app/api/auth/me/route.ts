import { NextResponse } from "next/server";

import { apiBaseUrl, sessionToken } from "@/lib/server";

export async function GET() {
  const token = await sessionToken();
  if (!token) {
    return NextResponse.json({ error: { code: "unauthorized", message: "Authentication required" } }, { status: 401 });
  }
  const upstream = await fetch(`${apiBaseUrl()}/api/auth/me`, {
    headers: { Authorization: `Bearer ${token}` },
    cache: "no-store",
  });
  const body = await upstream.json();
  return NextResponse.json(body, { status: upstream.status });
}
