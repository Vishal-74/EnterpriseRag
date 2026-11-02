import { NextResponse, type NextRequest } from "next/server";

const PROTECTED = ["/dashboard", "/documents", "/chat", "/agent", "/logs", "/settings"];

export function middleware(request: NextRequest) {
  const signedIn = Boolean(request.cookies.get("ei_session")?.value);
  const path = request.nextUrl.pathname;
  const needsAuth = PROTECTED.some((prefix) => path === prefix || path.startsWith(`${prefix}/`));
  if (needsAuth && !signedIn) {
    const login = new URL("/login", request.url);
    login.searchParams.set("next", path);
    return NextResponse.redirect(login);
  }
  if ((path === "/login" || path === "/register") && signedIn) {
    return NextResponse.redirect(new URL("/dashboard", request.url));
  }
  return NextResponse.next();
}

export const config = {
  matcher: ["/dashboard/:path*", "/documents/:path*", "/chat/:path*", "/agent/:path*", "/logs/:path*", "/settings/:path*", "/login", "/register"],
};
