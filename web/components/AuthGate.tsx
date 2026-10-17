"use client";

import { useState } from "react";
import { InternAvatar } from "@/components/InternAvatar";
import { useUser } from "@/lib/user";

function SignIn() {
  const { signIn, error } = useUser();
  const [email, setEmail] = useState("");
  const [sent, setSent] = useState(false);
  const [problem, setProblem] = useState<string | null>(null);

  return (
    <div className="mx-auto max-w-sm space-y-4 rounded-2xl bg-white p-6 shadow-sm ring-1 ring-brand-100">
      <InternAvatar mood="hello" size={80} />
      <h1 className="text-lg font-semibold text-cap-900">Sign in</h1>
      {sent ? (
        <p className="text-sm text-stone-600">Check {email} for a sign-in link. You can close this tab.</p>
      ) : (
        <form
          className="space-y-3"
          onSubmit={async (e) => {
            e.preventDefault();
            setProblem(null);
            try {
              await signIn(email.trim());
              setSent(true);
            } catch (err) {
              setProblem(err instanceof Error ? err.message : String(err));
            }
          }}
        >
          <label className="block space-y-1 text-sm">
            <span>Work email</span>
            <input type="email" required value={email} onChange={(e) => setEmail(e.target.value)} autoComplete="email"
                   className="w-full rounded-md border border-stone-300 px-2.5 py-1.5" />
          </label>
          <button type="submit" className="w-full rounded-md bg-stone-900 px-3 py-1.5 text-sm font-medium text-white">Email me a link</button>
          <p className="text-xs text-stone-500">Accounts are set up by your administrator.</p>
        </form>
      )}
      {(problem || error) && <p className="text-sm text-red-700">{problem ?? error}</p>}
    </div>
  );
}

export function AuthGate({ children }: { children: React.ReactNode }) {
  const { mode, signedOut, user } = useUser();
  if (mode === "supabase" && signedOut) return <SignIn />;
  return (
    <>
      {user?.synthetic && (
        <p className="mb-6 rounded-md border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-900">
          {user.org} is a synthetic organisation. Its numbers are for trying the product, not evidence about any real team.
        </p>
      )}
      {children}
    </>
  );
}
