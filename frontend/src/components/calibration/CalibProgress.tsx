import { useAppStore } from "@/stores/appStore";

export default function CalibProgress() {
  const { calibProgress, calibStatus } = useAppStore();

  // Find the latest progress event with rmse data
  const latestProgress = [...calibProgress]
    .reverse()
    .find((e) => e.type === "progress");
  const latestPhase = [...calibProgress]
    .reverse()
    .find((e) => e.type === "phase");
  const errorEvent = calibProgress.find((e) => e.type === "error");

  const currentStart = latestProgress?.start ?? 0;
  const totalStarts = latestProgress?.n_starts ?? 0;
  const iteration = latestProgress?.iter ?? 0;
  const rmse = latestProgress?.rmse ?? null;
  const elapsed = latestProgress?.elapsed ?? null;

  const progressPercent =
    totalStarts > 0 ? Math.round((currentStart / totalStarts) * 100) : 0;

  return (
    <div className="space-y-4">
      <h3 className="text-sm font-semibold text-foreground">
        Calibration in Progress
      </h3>

      {/* Progress bar */}
      <div className="space-y-1">
        <div className="h-2 w-full rounded-full bg-muted overflow-hidden">
          <div
            className="h-full rounded-full bg-primary transition-all duration-300"
            style={{ width: `${progressPercent}%` }}
          />
        </div>
        <div className="flex justify-between text-xs text-muted-foreground">
          <span>
            Start {currentStart} / {totalStarts}
          </span>
          <span>{progressPercent}%</span>
        </div>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-3 gap-4">
        <StatCard label="Iteration" value={iteration !== null ? String(iteration) : "--"} />
        <StatCard
          label="RMSE"
          value={rmse !== null ? `${rmse.toFixed(3)} degC` : "--"}
        />
        <StatCard
          label="Elapsed"
          value={elapsed !== null ? `${elapsed.toFixed(1)}s` : "--"}
        />
      </div>

      {/* Phase message */}
      {latestPhase?.message && (
        <div className="rounded-md border border-border bg-muted/30 px-3 py-2">
          <p className="text-xs text-muted-foreground">{latestPhase.message}</p>
        </div>
      )}

      {/* Error */}
      {calibStatus === "error" && errorEvent?.message && (
        <div className="rounded-md border border-destructive/50 bg-destructive/10 px-3 py-2">
          <p className="text-xs text-destructive">{errorEvent.message}</p>
        </div>
      )}

      {/* Progress log */}
      {calibProgress.length > 0 && (
        <div className="max-h-32 overflow-y-auto rounded-md border border-border bg-muted/20 p-2">
          {calibProgress
            .filter((e) => e.type === "progress" || e.type === "phase")
            .map((event, i) => (
              <p key={i} className="text-xs font-mono text-muted-foreground">
                {event.type === "phase" && event.message}
                {event.type === "progress" &&
                  `Start ${event.start}/${event.n_starts} | iter=${event.iter} | RMSE=${event.rmse?.toFixed(3) ?? "--"} | ${event.elapsed?.toFixed(1) ?? "--"}s`}
              </p>
            ))}
        </div>
      )}
    </div>
  );
}

function StatCard({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-md border border-border bg-card p-2 text-center">
      <p className="text-xs text-muted-foreground">{label}</p>
      <p className="text-sm font-mono tabular-nums font-medium">{value}</p>
    </div>
  );
}
