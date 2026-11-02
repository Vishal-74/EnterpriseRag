import { NextResponse } from "next/server";

import { SESSION_COOKIE } from "@/lib/server";

export async function POST() {
  const response = new NextResponse(null, { status: 204 });
  response.cookies.set(SESSION_COOKIE, "", { httpOnly: true, path: "/", maxAge: 0 });
  return response;
}
