"use client";

import { useEffect, useState } from "react";
import { api, ApiError, type TaskTypeInfo } from "@/lib/api";
import { useUser } from "@/lib/user";

/** The org's task types and the selected one, kept valid as users switch. */
export function useTaskTypes() {
  const { user } = useUser();
  const [taskTypes, setTaskTypes] = useState<TaskTypeInfo[]>([]);
  const [taskTypeId, setTaskTypeId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!user) return;
    api.taskTypes().then((tts) => {
      setTaskTypes(tts);
      setTaskTypeId((id) => (id && tts.some((t) => t.id === id) ? id : (tts[0]?.id ?? null)));
    }).catch((e) => setError(e instanceof ApiError ? e.message : String(e)));
  }, [user]);

  return { user, taskTypes, taskTypeId, setTaskTypeId, taskType: taskTypes.find((t) => t.id === taskTypeId), error };
}
