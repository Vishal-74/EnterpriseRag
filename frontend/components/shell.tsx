"use client";

import { Bot, FileStack, LayoutDashboard, LogOut, MessagesSquare, ScrollText, Settings } from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";

import { api } from "@/lib/api";

const LINKS = [
  { href: "/dashboard", label: "Overview", icon: LayoutDashboard },
  { href: "/documents", label: "Documents", icon: FileStack },
  { href: "/chat", label: "Ask", icon: MessagesSquare },
  { href: "/agent", label: "Agent", icon: Bot },
  { href: "/logs", label: "Activity", icon: ScrollText },
  { href: "/settings", label: "Settings", icon: Settings },
];

export function Shell({ email, children }: { email: string; children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();

  async function logout() {
    await api.logout();
    router.replace("/login");
    router.refresh();
  }

  return (
    <div className="min-h-screen md:grid md:grid-cols-[240px_1fr]">
      <aside className="border-b border-line bg-[#f7f3eb] px-4 py-5 md:min-h-screen md:border-b-0 md:border-r">
        <Link href="/dashboard" className="block px-2">
          <p className="font-display text-2xl tracking-tight">Meridian</p>
          <p className="text-xs uppercase tracking-[0.18em] text-mist">Document intelligence</p>
        </Link>
        <nav className="mt-8 flex gap-2 overflow-x-auto md:flex-col">
          {LINKS.map((link) => {
            const active = pathname === link.href || pathname.startsWith(`${link.href}/`);
            const Icon = link.icon;
            return (
              <Link
                key={link.href}
                href={link.href}
                className={`flex items-center gap-2 rounded-full px-3 py-2 text-sm ${
                  active ? "bg-ink text-paper" : "text-ink hover:bg-white"
                }`}
              >
                <Icon size={16} />
                {link.label}
              </Link>
            );
          })}
        </nav>
        <div className="mt-6 hidden items-center justify-between gap-3 px-2 text-sm md:flex">
          <span className="truncate text-mist">{email}</span>
          <button aria-label="Log out" onClick={logout} type="button">
            <LogOut size={16} />
          </button>
        </div>
      </aside>
      <main className="min-w-0 max-w-full overflow-x-hidden px-4 py-6 md:px-10 md:py-8">{children}</main>
    </div>
  );
}
