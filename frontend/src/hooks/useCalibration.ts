import { useEffect, useRef, useCallback } from "react";
import { calibrationApi } from "@/lib/api";
import { useAppStore } from "@/stores/appStore";
import type { CalibRequest, CalibProgressEvent } from "@/types/calibration";

/**
 * Hook to start a calibration and subscribe to SSE progress events.
 * Returns a start function and current calibration state.
 */
export function useCalibration() {
  const {
    calibJobId,
    calibStatus,
    calibProgress,
    calibResult,
    calibError,
    startCalib,
    updateProgress,
    finishCalib,
    errorCalib,
    resetCalib,
  } = useAppStore();

  const cleanupRef = useRef<(() => void) | null>(null);

  // Subscribe to SSE when status is "running"
  useEffect(() => {
    if (calibStatus !== "running" || !calibJobId) return;

    const cleanup = calibrationApi.streamProgress(
      calibJobId,
      (event: CalibProgressEvent) => {
        updateProgress(event);
        if (event.type === "done" && event.result) {
          finishCalib(event.result);
        }
        if (event.type === "error") {
          errorCalib(event.message ?? "Unknown calibration error");
        }
      },
      () => {
        errorCalib("SSE connection lost");
      },
    );

    cleanupRef.current = cleanup;
    return () => {
      cleanup();
      cleanupRef.current = null;
    };
  }, [calibStatus, calibJobId, updateProgress, finishCalib, errorCalib]);

  const start = useCallback(
    async (request: CalibRequest) => {
      try {
        resetCalib();
        const jobId = await calibrationApi.start(request);
        startCalib(jobId);
      } catch (err: unknown) {
        errorCalib(
          `Failed to start calibration: ${err instanceof Error ? err.message : "Unknown error"}`,
        );
      }
    },
    [resetCalib, startCalib, errorCalib],
  );

  return {
    status: calibStatus,
    jobId: calibJobId,
    progress: calibProgress,
    result: calibResult,
    error: calibError,
    start,
    reset: resetCalib,
  };
}
