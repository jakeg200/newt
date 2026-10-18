"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { isPublic } from "@/components/AuthGate";
import { InternAvatar } from "@/components/InternAvatar";
import { BRAND } from "@/lib/brand";
import { useUser } from "@/lib/user";

// Four places, around what a person needs, not the machinery. Detailed screens live under Setup.
const NAV = [
  { href: "/", label: "Home", match: ["/"] },
  { href: "/inbox", label: "Needs you", match: ["/inbox", "/today", "/autonomy"] },
  { href: "/report", label: "Report card", match: ["/report", "/board"] },
  { href: "/setup", label: "Setup", match: ["/setup", "/orientation", "/capture", "/backtest", "/learned", "/manager"] },
];

export function Header() {
  const { mode, users, user, setUser, signOut, error } = useUser();
  const pathname = usePathname();

  if (isPublic(pathname)) {
    return (
      <header className="sticky top-0 z-30 px-3 pt-3 sm:px-6">
        <div className="mx-auto flex max-w-6xl items-center gap-4 rounded-3xl border border-stone-200 bg-white/90 px-4 py-2.5 shadow-[0_8px_30px_-16px_rgb(27_23_20/0.35)] backdrop-blur">
          <Link href="/welcome" className="flex items-center gap-2 font-[family-name:var(--font-display)] text-lg font-extrabold tracking-tight">
            <InternAvatar size={28} decorative />
            {BRAND}
          </Link>
          <nav className="ml-auto hidden gap-1 text-sm sm:flex" aria-label="Sections">
            <a href="#how" className="rounded-full px-3 py-1.5 text-stone-600 hover:bg-stone-100">How it works</a>
            <a href="#trust" className="rounded-full px-3 py-1.5 text-stone-600 hover:bg-stone-100">Why trust it</a>
          </nav>
          <Link href="/" className="ml-auto rounded-full bg-ink px-4 py-2 text-sm font-semibold text-white sm:ml-0">Open the app</Link>
        </div>
      </header>
    );
  }

  return (
    <header className="sticky top-0 z-30 px-3 pt-3 sm:px-6">
      <div className="mx-auto flex max-w-6xl flex-wrap items-center gap-x-4 gap-y-2 rounded-3xl border border-stone-200 bg-white/90 px-4 py-2.5 shadow-[0_8px_30px_-16px_rgb(27_23_20/0.35)] backdrop-blur">
        <Link href="/" className="flex items-center gap-2 font-[family-name:var(--font-display)] text-lg font-extrabold tracking-tight">
          <InternAvatar size={28} decorative />
          {BRAND}
        </Link>
        <nav className="order-3 -mx-1 flex w-full gap-1 overflow-x-auto text-sm lg:order-none lg:w-auto" aria-label="Main">
          {NAV.map((item) => {
            const on = item.match.some((m) => (m === "/" ? pathname === "/" : pathname.startsWith(m)));
            return (
              <Link
                key={item.href}
                href={item.href}
                aria-current={on ? "page" : undefined}
                className={`shrink-0 rounded-full px-3 py-1.5 transition-colors ${on ? "bg-ink font-medium text-white" : "text-stone-600 hover:bg-stone-100 hover:text-ink"}`}
              >
                {item.label}
              </Link>
            );
          })}
        </nav>
        <div className="ml-auto flex items-center gap-2 text-sm">
          {mode === "supabase" ? (
            user && (
              <>
                <span className="text-stone-600">{user.name}</span>
                <button type="button" onClick={() => signOut()} className="rounded-full px-3 py-1.5 text-stone-500 hover:bg-stone-100">
                  Sign out
                </button>
              </>
            )
          ) : error ? (
            <span className="text-red-700">{error}</span>
          ) : (
            <>
              <label htmlFor="dev-user" className="hidden text-stone-500 sm:inline">Acting as</label>
              <select
                id="dev-user"
                value={user?.id ?? ""}
                onChange={(e) => setUser(e.target.value)}
                className="max-w-52 rounded-full border border-stone-200 bg-stone-50 px-3 py-1.5"
              >
                {users.map((u) => (
                  <option key={u.id} value={u.id}>
                    {u.name} · {u.role} · {u.org}
                  </option>
                ))}
              </select>
            </>
          )}
        </div>
      </div>
    </header>
  );
}
