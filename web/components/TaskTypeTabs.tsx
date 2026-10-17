"use client";

import type { TaskTypeInfo } from "@/lib/api";

export function TaskTypeTabs({ taskTypes, value, onChange }: { taskTypes: TaskTypeInfo[]; value: string | null; onChange: (id: string) => void }) {
  if (taskTypes.length < 2) return null;
  return (
    <div className="flex gap-1 rounded-lg bg-stone-200/60 p-1 text-sm" role="tablist" aria-label="Task type">
      {taskTypes.map((t) => (
        <button
          key={t.id}
          role="tab"
          aria-selected={t.id === value}
          onClick={() => onChange(t.id)}
          className={`rounded-md px-3 py-1 ${t.id === value ? "bg-white font-medium shadow-sm" : "text-stone-600"}`}
        >
          {t.name}
        </button>
      ))}
    </div>
  );
}
