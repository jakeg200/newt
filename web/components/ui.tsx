import type { ReactNode } from "react";
import { InternAvatar, type Growth, type Mood } from "@/components/InternAvatar";

/** Big display title, a short intro, and optionally the intern in the mood of this page. */
export function PageHeader({ title, intro, mood, aside }: { title: ReactNode; intro?: ReactNode; mood?: Mood; aside?: ReactNode }) {
  return (
    <div className="flex flex-wrap items-end justify-between gap-4 animate-rise">
      <div className="flex items-center gap-4">
        {mood && <InternAvatar mood={mood} size={72} className="hidden shrink-0 sm:block" />}
        <div className="space-y-1.5">
          <h1 className="text-3xl sm:text-4xl">{title}</h1>
          {intro && <p className="max-w-2xl text-stone-600">{intro}</p>}
        </div>
      </div>
      {aside}
    </div>
  );
}

/** A message from the intern, styled like a chat notification. */
export function Bubble({ name, mood = "neutral", growth, time, children }: {
  name: string; mood?: Mood; growth?: Growth; time?: string; children: ReactNode;
}) {
  return (
    <div className="flex items-start gap-3 rounded-2xl border border-stone-200 bg-white p-3.5 shadow-[0_6px_24px_-14px_rgb(27_23_20/0.3)]">
      <InternAvatar mood={mood} growth={growth} size={48} decorative className="shrink-0" animated={false} />
      <div className="min-w-0 text-sm">
        <p className="flex items-baseline gap-2">
          <span className="font-semibold">{name}</span>
          {time && <span className="text-xs text-stone-400">{time}</span>}
        </p>
        <div className="text-stone-700">{children}</div>
      </div>
    </div>
  );
}
