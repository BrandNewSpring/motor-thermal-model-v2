import { useMemo } from "react";
import Plotly from "plotly.js-dist-min";
// @MX:NOTE: react-plotly.js/factory is CJS — Vite's esbuild pre-bundle wraps the default
// export as { default: fn, __esModule: true }. Must unwrap .default to get the actual function.
import createPlotlyComponentCJS from "react-plotly.js/factory";
import type { CalibResult, FileCalibResult } from "@/types/calibration";

const createPlotlyComponent =
  typeof createPlotlyComponentCJS === "function"
    ? createPlotlyComponentCJS
    : (createPlotlyComponentCJS as unknown as { default: (p: typeof Plotly) => React.ComponentType<Record<string, unknown>> }).default;

const Plot = createPlotlyComponent(Plotly);
import { useAppStore } from "@/stores/appStore";
import { exportApi } from "@/lib/api";
import { Download } from "lucide-react";

// Downsample arrays for Plotly performance
const MAX_POINTS = 2000;
function downsample(arr: number[], max: number): number[] {
  if (arr.length <= max) return arr;
  const step = arr.length / max;
  const result: number[] = [];
  for (let i = 0; i < max; i++) {
    result.push(arr[Math.floor(i * step)]);
  }
  return result;
}

interface CalibResultsProps {
  result: CalibResult;
}

export default function CalibResults({ result }: CalibResultsProps) {
  const { currentProfileId, calibJobId } = useAppStore();
  const { params, rmse, r_squared, T_coil_sim, T_core_sim, T_housing_sim, T_coil_meas, time_array, time_s, converged, per_file_results } = result;

  // Downsample all arrays together (same indices)
  const chartData = useMemo(() => {
    const n = T_coil_sim.length;
    if (n === 0) return null;

    const time = downsample(time_array, MAX_POINTS);
    const coilSim = downsample(T_coil_sim, MAX_POINTS);
    const coreSim = downsample(T_core_sim, MAX_POINTS);
    const housingSim = downsample(T_housing_sim, MAX_POINTS);
    const coilMeas = T_coil_meas.length > 0 ? downsample(T_coil_meas, MAX_POINTS) : null;

    return { time, coilSim, coreSim, housingSim, coilMeas };
  }, [T_coil_sim, T_core_sim, T_housing_sim, T_coil_meas, time_array]);

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

      {/* Per-file Temperature Comparison Charts */}
      {per_file_results.length > 0 ? (
        <div className="space-y-4">
          {per_file_results.map((fileResult) => (
            <PerFileChart key={fileResult.file_id} fileResult={fileResult} />
          ))}
        </div>
      ) : (
        chartData && (
          <div className="rounded-md border border-border bg-muted/20 p-4">
            <h4 className="text-xs font-semibold text-foreground mb-2">
              Temperature Comparison
            </h4>
            <Plot
              data={[
                ...(chartData.coilMeas
                  ? [{
                      x: chartData.time,
                      y: chartData.coilMeas,
                      type: "scatter" as const,
                      mode: "lines" as const,
                      name: "Measured T_coil",
                      line: { color: "rgba(0,0,0,0.4)", width: 1, dash: "dot" as const },
                    }]
                  : []),
                {
                  x: chartData.time,
                  y: chartData.coilSim,
                  type: "scatter" as const,
                  mode: "lines" as const,
                  name: "Simulated T_coil",
                  line: { color: "hsl(217, 91%, 60%)", width: 2 },
                },
                {
                  x: chartData.time,
                  y: chartData.coreSim,
                  type: "scatter" as const,
                  mode: "lines" as const,
                  name: "Simulated T_core",
                  line: { color: "hsl(142, 71%, 45%)", width: 1.5 },
                },
                {
                  x: chartData.time,
                  y: chartData.housingSim,
                  type: "scatter" as const,
                  mode: "lines" as const,
                  name: "Simulated T_housing",
                  line: { color: "hsl(30, 90%, 50%)", width: 1.5 },
                },
              ]}
              layout={{
                autosize: true,
                height: 350,
                margin: { l: 50, r: 20, t: 10, b: 40 },
                xaxis: { title: "Time [s]", gridcolor: "rgba(0,0,0,0.06)" },
                yaxis: { title: "Temperature [degC]", gridcolor: "rgba(0,0,0,0.06)" },
                legend: { orientation: "h", y: -0.15, x: 0.5, xanchor: "center" },
                paper_bgcolor: "transparent",
                plot_bgcolor: "transparent",
                font: { size: 11 },
                showlegend: true,
              }}
              config={{
                responsive: true,
                displayModeBar: true,
                modeBarButtonsToRemove: ["lasso2d", "select2d"],
                displaylogo: false,
              }}
              className="w-full"
            />
          </div>
        )
      )}
    </div>
  );
}

function PerFileChart({ fileResult }: { fileResult: FileCalibResult }) {
  const { filename, conditions, time_array, T_coil_meas, T_coil_sim, T_core_sim, T_housing_sim } = fileResult;

  const time = downsample(time_array, MAX_POINTS);
  const coilSim = downsample(T_coil_sim, MAX_POINTS);
  const coreSim = downsample(T_core_sim, MAX_POINTS);
  const housingSim = downsample(T_housing_sim, MAX_POINTS);
  const coilMeas = T_coil_meas.length > 0 ? downsample(T_coil_meas, MAX_POINTS) : null;

  // Build conditions subtitle
  const condParts: string[] = [];
  if (conditions.I_mean != null) condParts.push(`I=${conditions.I_mean.toFixed(1)}A`);
  if (conditions.T_amb_mean != null) condParts.push(`T_amb=${conditions.T_amb_mean.toFixed(1)}°C`);
  if (conditions.rpm_representative != null) condParts.push(`RPM=${Math.round(conditions.rpm_representative)}`);

  return (
    <div className="rounded-md border border-border bg-muted/20 p-4">
      <h4 className="text-xs font-semibold text-foreground mb-1">
        {filename}
      </h4>
      {condParts.length > 0 && (
        <p className="text-xs text-muted-foreground mb-2">
          {condParts.join(", ")}
        </p>
      )}
      <Plot
        data={[
          ...(coilMeas
            ? [{
                x: time,
                y: coilMeas,
                type: "scatter" as const,
                mode: "lines" as const,
                name: "Measured T_coil",
                line: { color: "rgba(0,0,0,0.4)", width: 1, dash: "dot" as const },
              }]
            : []),
          {
            x: time,
            y: coilSim,
            type: "scatter" as const,
            mode: "lines" as const,
            name: "Simulated T_coil",
            line: { color: "hsl(217, 91%, 60%)", width: 2 },
          },
          {
            x: time,
            y: coreSim,
            type: "scatter" as const,
            mode: "lines" as const,
            name: "Simulated T_core",
            line: { color: "hsl(142, 71%, 45%)", width: 1.5 },
          },
          {
            x: time,
            y: housingSim,
            type: "scatter" as const,
            mode: "lines" as const,
            name: "Simulated T_housing",
            line: { color: "hsl(30, 90%, 50%)", width: 1.5 },
          },
        ]}
        layout={{
          autosize: true,
          height: 350,
          margin: { l: 50, r: 20, t: 10, b: 40 },
          xaxis: { title: "Time [s]", gridcolor: "rgba(0,0,0,0.06)" },
          yaxis: { title: "Temperature [degC]", gridcolor: "rgba(0,0,0,0.06)" },
          legend: { orientation: "h", y: -0.15, x: 0.5, xanchor: "center" },
          paper_bgcolor: "transparent",
          plot_bgcolor: "transparent",
          font: { size: 11 },
          showlegend: true,
        }}
        config={{
          responsive: true,
          displayModeBar: true,
          modeBarButtonsToRemove: ["lasso2d", "select2d"],
          displaylogo: false,
        }}
        className="w-full"
      />
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
