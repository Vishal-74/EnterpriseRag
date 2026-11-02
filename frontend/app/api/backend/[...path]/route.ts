import { NextResponse } from "next/server";

import { apiBaseUrl, sessionToken } from "@/lib/server";

async function forward(request: Request, path: string[]) {
  const token = await sessionToken();
  if (!token) {
    return NextResponse.json(
      { error: { code: "unauthorized", message: "Authentication required" } },
      { status: 401 },
    );
  }
  const incoming = new URL(request.url);
  const target = `${apiBaseUrl()}/api/${path.join("/")}${incoming.search}`;
  const headers = new Headers();
  headers.set("Authorization", `Bearer ${token}`);
  const contentType = request.headers.get("content-type");
  if (contentType) {
    headers.set("content-type", contentType);
  }
  const method = request.method.toUpperCase();
  const body = method === "GET" || method === "HEAD" ? undefined : await request.arrayBuffer();
  const upstream = await fetch(target, { method, headers, body, cache: "no-store" });
  if (upstream.status === 204) {
    return new NextResponse(null, { status: 204 });
  }
  const responseBody = await upstream.arrayBuffer();
  return new NextResponse(responseBody, {
    status: upstream.status,
    headers: { "content-type": upstream.headers.get("content-type") || "application/json" },
  });
}

type Context = { params: Promise<{ path: string[] }> };

export async function GET(request: Request, context: Context) {
  return forward(request, (await context.params).path);
}

export async function POST(request: Request, context: Context) {
  return forward(request, (await context.params).path);
}

export async function DELETE(request: Request, context: Context) {
  return forward(request, (await context.params).path);
}
