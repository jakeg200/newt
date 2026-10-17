"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useUser } from "@/lib/user";

const NAV = [
  { href: "/orientation", label: "Orientation", ready: true },
  { href: "/capture", label: "Capture", ready: true },
  { href: "/backtest", label: "Backtest", ready: true },
  { href: "/today", label: "Today", ready: true },
  { href: "/learned", label: "What I've learned", ready: true },
  { href: "#", label: "Task board", ready: false },
  { href: "#", label: "Manager", ready: false },
];

export function Header() {
  const { users, user, setUser, error } = useUser();
  const pathname = usePathname();

  return (
    <header className="border-b border-stone-200 bg-white">
      <div className="mx-auto flex max-w-6xl flex-wrap items-center gap-x-6 gap-y-3 px-4 py-3 sm:px-6">
        <Link href="/" className="font-semibold tracking-tight">
          Agent Onboarding
        </Link>
        <nav className="flex flex-wrap gap-1 text-sm">
          {NAV.map((item) =>
            item.ready ? (
              <Link
                key={item.label}
                href={item.href}
                className={`rounded-md px-2.5 py-1.5 ${
                  pathname.startsWith(item.href) ? "bg-stone-100 font-medium" : "text-stone-600 hover:bg-stone-50"
                }`}
              >
                {item.label}
              </Link>
            ) : (
              <span key={item.label} className="cursor-default px-2.5 py-1.5 text-stone-400" title="Coming in a later milestone">
                {item.label}
              </span>
            ),
          )}
        </nav>
        <div className="ml-auto flex items-center gap-2 text-sm">
          {error ? (
            <span className="text-red-700">{error}</span>
          ) : (
            <>
              <label htmlFor="dev-user" className="text-stone-500">
                Acting as
              </label>
              <select
                id="dev-user"
                value={user?.id ?? ""}
                onChange={(e) => setUser(e.target.value)}
                className="rounded-md border border-stone-300 bg-white px-2 py-1.5"
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
