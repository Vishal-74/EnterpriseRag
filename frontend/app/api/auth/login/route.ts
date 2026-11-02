import { NextResponse } from "next/server";

import { apiBaseUrl, cookieOptions, SESSION_COOKIE } from "@/lib/server";

export async function POST(request: Request) {
  const payload = await request.json();
  const upstream = await fetch(`${apiBaseUrl()}/api/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  const body = await upstream.json();
  if (!upstream.ok) {
    return NextResponse.json(body, { status: upstream.status });
  }
  const response = NextResponse.json({ user: body.user });
  response.cookies.set(SESSION_COOKIE, body.access_token, cookieOptions());
  return response;
}
