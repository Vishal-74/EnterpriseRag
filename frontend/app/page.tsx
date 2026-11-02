import { redirect } from "next/navigation";

import { sessionToken } from "@/lib/server";

export default async function HomePage() {
  const token = await sessionToken();
  redirect(token ? "/dashboard" : "/login");
}
