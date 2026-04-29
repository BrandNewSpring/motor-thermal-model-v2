import type { CalibResult } from "@/types/calibration";
import { useAppStore } from "@/stores/appStore";
import { exportApi } from "@/lib/api";
import { Download } from "lucide-react";

interface CalibResultsProps {
  result: CalibResult;
  timeData?: number[];
  measuredCoil?: number[];
}

export default function CalibResults({
  result,
  timeData: _timeData,
  measuredCoil: _measuredCoil,
}: CalibResultsProps) {
  void _timeData;
  void _measuredCoil;
  const { currentProfileId, calibJobId } = useAppStore();
  const { params, rmse, r_squared, T_coil_sim, T_core_sim, T_housing_sim, time_s, converged } = result;

  async function handleExport() {
    if (!currentProfileId) return;
    await exportApi.excel({
      profile_id: currentProfileId,
      job_id: calibJobId ?? undefined,
      include_grid: false,
    });
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-semibold text-foreground">
          Calibration Results
        </h3>
        <button
          type="button"
          onClick={() => void handleExport()}
          className="inline-flex items-center gap-1.5 rounded-md border border-input bg-background px-3 py-1.5 text-xs font-medium hover:bg-muted transition-colors"
        >
          <Download className="size-3.5" />
          Export Excel
        </button>
      </div>

      {/* Convergence status */}
      <div
        className={`rounded-md border px-3 py-2 text-xs ${
          converged
            ? "border-green-500/30 bg-green-500/10 text-green-700"
            : "border-yellow-500/30 bg-yellow-500/10 text-yellow-700"
        }`}
      >
        {converged
          ? `Converged in ${time_s.toFixed(1)}s`
          : `Did not fully converge (${time_s.toFixed(1)}s elapsed)`}
      </div>

      {/* Parameter Cards */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        <ParamCard label="R1" value={params.R1} unit="degC/W" />
        <ParamCard label="R2" value={params.R2} unit="degC/W" />
        <ParamCard label="h_nat" value={params.h_nat} unit="W/(m2*K)" />
        <ParamCard label="h_rpm" value={params.h_rpm} unit="W/(m2*K/sqrt(RPM))" />
      </div>

      {/* Quality metrics */}
      <div className="grid grid-cols-2 gap-3">
        <MetricCard label="RMSE" value={`${rmse.toFixed(3)} degC`} />
        <MetricCard label="R-squared" value={r_squared.toFixed(4)} />
      </div>

      {/* Thermal Network Diagram */}
      <div className="rounded-md border border-border bg-muted/20 p-4">
        <h4 className="text-xs font-semibold text-foreground mb-3">
          Thermal Network
        </h4>
        <svg
          viewBox="0 0 600 80"
          className="w-full h-auto"
          role="img"
          aria-label="Thermal resistance network diagram"
        >
          {/* Nodes */}
          <rect x="10" y="20" width="90" height="40" rx="4" fill="hsl(217, 91%, 60%)" opacity="0.15" stroke="hsl(217, 91%, 60%)" strokeWidth="1" />
          <text x="55" y="45" textAnchor="middle" fontSize="11" fill="currentColor">Coil</text>

          <rect x="170" y="20" width="90" height="40" rx="4" fill="hsl(142, 71%, 45%)" opacity="0.15" stroke="hsl(142, 71%, 45%)" strokeWidth="1" />
          <text x="215" y="45" textAnchor="middle" fontSize="11" fill="currentColor">Core</text>

          <rect x="330" y="20" width="90" height="40" rx="4" fill="hsl(30, 90%, 50%)" opacity="0.15" stroke="hsl(30, 90%, 50%)" strokeWidth="1" />
          <text x="375" y="45" textAnchor="middle" fontSize="11" fill="currentColor">Housing</text>

          <rect x="490" y="20" width="90" height="40" rx="4" fill="hsl(0, 0%, 80%)" opacity="0.15" stroke="hsl(0, 0%, 80%)" strokeWidth="1" />
          <text x="535" y="45" textAnchor="middle" fontSize="11" fill="currentColor">Ambient</text>

          {/* Resistances */}
          <line x1="100" y1="40" x2="170" y2="40" stroke="currentColor" strokeWidth="2" />
          <text x="135" y="32" textAnchor="middle" fontSize="9" fill="currentColor" fontFamily="monospace">R1</text>
          <text x="135" y="58" textAnchor="middle" fontSize="8" fill="hsl(0,0%,50%)" fontFamily="monospace">{params.R1.toFixed(3)}</text>

          <line x1="260" y1="40" x2="330" y2="40" stroke="currentColor" strokeWidth="2" />
          <text x="295" y="32" textAnchor="middle" fontSize="9" fill="currentColor" fontFamily="monospace">R2</text>
          <text x="295" y="58" textAnchor="middle" fontSize="8" fill="hsl(0,0%,50%)" fontFamily="monospace">{params.R2.toFixed(3)}</text>

          <line x1="420" y1="40" x2="490" y2="40" stroke="currentColor" strokeWidth="2" />
          <text x="455" y="32" textAnchor="middle" fontSize="9" fill="currentColor" fontFamily="monospace">R3(RPM)</text>

          {/* Capacitances */}
          <text x="55" y="72" textAnchor="middle" fontSize="8" fill="hsl(0,0%,50%)" fontFamily="monospace">C={params.C_coil.toFixed(1)}</text>
          <text x="215" y="72" textAnchor="middle" fontSize="8" fill="hsl(0,0%,50%)" fontFamily="monospace">C={params.C_core.toFixed(1)}</text>
          <text x="375" y="72" textAnchor="middle" fontSize="8" fill="hsl(0,0%,50%)" fontFamily="monospace">C={params.C_housing.toFixed(1)}</text>
        </svg>
      </div>

      {/* Temperature Comparison Chart placeholder */}
      <div className="rounded-md border border-border bg-muted/20 p-4">
        <h4 className="text-xs font-semibold text-foreground mb-2">
          Temperature Comparison
        </h4>
        <div
          data-chart="temperature"
          data-coil-sim={JSON.stringify(T_coil_sim.slice(0, 20))}
          data-core-sim={JSON.stringify(T_core_sim.slice(0, 20))}
          data-housing-sim={JSON.stringify(T_housing_sim.slice(0, 20))}
          data-measured={_measuredCoil ? JSON.stringify(_measuredCoil.slice(0, 20)) : undefined}
          className="w-full h-64 bg-background rounded flex items-center justify-center text-xs text-muted-foreground"
        >
          Chart renders at runtime (Plotly)
        </div>
      </div>
    </div>
  );
}

function ParamCard({
  label,
  value,
  unit,
}: {
  label: string;
  value: number;
  unit: string;
}) {
  return (
    <div className="rounded-md border border-border bg-card p-3">
      <p className="text-xs text-muted-foreground">{label}</p>
      <p className="text-lg font-mono tabular-nums font-semibold">
        {value.toFixed(4)}
      </p>
      <p className="text-xs text-muted-foreground">{unit}</p>
    </div>
  );
}

function MetricCard({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-md border border-border bg-card p-3">
      <p className="text-xs text-muted-foreground">{label}</p>
      <p className="text-sm font-mono tabular-nums font-semibold">{value}</p>
    </div>
  );
}
