"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { InternAvatar } from "@/components/InternAvatar";
import { BRAND } from "@/lib/brand";
import { useUser } from "@/lib/user";

// Grouped by the intern's journey: onboard it, teach it, graduate it, manage it.
const NAV = [
  { href: "/orientation", label: "Orientation" },
  { href: "/capture", label: "Capture" },
  { href: "/today", label: "Today" },
  { href: "/learned", label: "Learned" },
  { href: "/backtest", label: "Backtest" },
  { href: "/board", label: "Task board" },
  { href: "/autonomy", label: "Autonomy" },
  { href: "/manager", label: "Manager" },
];

export function Header() {
  const { mode, users, user, setUser, signOut, error } = useUser();
  const pathname = usePathname();

  return (
    <header className="sticky top-0 z-30 px-3 pt-3 sm:px-6">
      <div className="mx-auto flex max-w-6xl flex-wrap items-center gap-x-4 gap-y-2 rounded-3xl border border-stone-200 bg-white/90 px-4 py-2.5 shadow-[0_8px_30px_-16px_rgb(27_23_20/0.35)] backdrop-blur">
        <Link href="/" className="flex items-center gap-2 font-[family-name:var(--font-display)] text-lg font-extrabold tracking-tight">
          <InternAvatar size={28} decorative />
          {BRAND}
        </Link>
        <nav className="order-3 -mx-1 flex w-full gap-1 overflow-x-auto text-sm lg:order-none lg:w-auto" aria-label="Main">
          {NAV.map((item) => {
            const on = pathname.startsWith(item.href);
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
