import { redirect } from "next/navigation";

import { Shell } from "@/components/shell";
import { apiBaseUrl, sessionToken } from "@/lib/server";

export const dynamic = "force-dynamic";

export default async function WorkspaceLayout({ children }: { children: React.ReactNode }) {
  const token = await sessionToken();
  if (!token) {
    redirect("/login");
  }
  const response = await fetch(`${apiBaseUrl()}/api/auth/me`, {
    headers: { Authorization: `Bearer ${token}` },
    cache: "no-store",
  });
  if (!response.ok) {
    redirect("/login");
  }
  const user = (await response.json()) as { email: string };
  return <Shell email={user.email}>{children}</Shell>;
}
