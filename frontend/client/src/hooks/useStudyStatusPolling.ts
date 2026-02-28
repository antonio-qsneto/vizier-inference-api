import { useCallback, useEffect, useState } from "react";
import { fetchStudyStatus } from "@/api/services";
import type { StudyStatus } from "@/types/api";

const TERMINAL_STUDY_STATUSES = new Set(["COMPLETED", "FAILED"]);

export function isTerminalStudyStatus(status: string | null | undefined) {
  return status ? TERMINAL_STUDY_STATUSES.has(status) : false;
}

interface UseStudyStatusPollingOptions {
  studyId: string | null;
  token: string | null;
  initialValue?: StudyStatus | null;
  enabled?: boolean;
  intervalMs?: number;
}

export function useStudyStatusPolling({
  studyId,
  token,
  initialValue = null,
  enabled = true,
  intervalMs = 5000,
}: UseStudyStatusPollingOptions) {
  const [value, setValue] = useState<StudyStatus | null>(initialValue);
  const [error, setError] = useState<string | null>(null);
  const [isRefreshing, setIsRefreshing] = useState(false);

  useEffect(() => {
    setValue(initialValue);
  }, [initialValue]);

  const refresh = useCallback(async () => {
    if (!studyId || !token) {
      return null;
    }

    setIsRefreshing(true);
    try {
      const nextValue = await fetchStudyStatus(token, studyId);
      setValue(nextValue);
      setError(null);
      return nextValue;
    } catch (requestError) {
      if (requestError instanceof Error) {
        setError(requestError.message);
      }
      return null;
    } finally {
      setIsRefreshing(false);
    }
  }, [studyId, token]);

  useEffect(() => {
    if (!enabled || !studyId || !token) {
      return;
    }

    let cancelled = false;
    let timerId = 0;

    const poll = async () => {
      const nextValue = await refresh();
      if (cancelled || !nextValue || isTerminalStudyStatus(nextValue.status)) {
        return;
      }
      timerId = window.setTimeout(poll, intervalMs);
    };

    if (!value || !isTerminalStudyStatus(value.status)) {
      void poll();
    }

    return () => {
      cancelled = true;
      window.clearTimeout(timerId);
    };
  }, [enabled, intervalMs, refresh, studyId, token, value]);

  return {
    value,
    error,
    isRefreshing,
    refresh,
  };
}
