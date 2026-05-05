import { useMemo } from "react";
import Plotly from "plotly.js-dist-min";
// @MX:NOTE: react-plotly.js/factory is CJS — Vite's esbuild pre-bundle wraps the default
// export as { default: fn, __esModule: true }. Must unwrap .default to get the actual function.
import createPlotlyComponentCJS from "react-plotly.js/factory";
import type {
  CompressorEnergyResponse,
  EnergyCalibResult,
} from "@/types/compressor";

const createPlotlyComponent =
  typeof createPlotlyComponentCJS === "function"
    ? createPlotlyComponentCJS
    : (createPlotlyComponentCJS as unknown as { default: (p: typeof Plotly) => React.ComponentType<Record<string, unknown>> }).default;

const Plot = createPlotlyComponent(Plotly);

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

export interface PredictionInputs {
  Ps: number; Ts: number;
  P_mid: number; T_mid: number;
  Pd: number; mdot: number;
  V: number; I: number; RPM: number;
}

interface CompressorResultsProps {
  prediction: CompressorEnergyResponse | null;
  calibResult: EnergyCalibResult | null;
  predictionInputs?: PredictionInputs | null;
}

export default function CompressorResults({
  prediction,
  calibResult,
  predictionInputs,
}: CompressorResultsProps) {
  if (!prediction && !calibResult) {
    return (
      <div className="rounded-md border border-border bg-muted/20 p-6 text-center">
        <p className="text-sm text-muted-foreground">
          Run a prediction or calibration to see results here.
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Prediction result */}
      {prediction && (
        <PredictionResults response={prediction} inputs={predictionInputs ?? null} />
      )}

      {/* Calibration result */}
      {calibResult && (
        <CalibrationResults result={calibResult} />
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Helpers for the prediction dashboard
// ---------------------------------------------------------------------------

function getMotorColor(temp: number): { fill: string; stroke: string } {
  if (temp > 120) return { fill: "#DC2626", stroke: "#B91C1C" }; // danger red
  if (temp > 80) return { fill: "#EA580C", stroke: "#C2410C" };   // warning red-orange
  return { fill: "#D97706", stroke: "#B45309" };                    // normal orange
}

function fmt(v: number, decimals = 1): string {
  return v.toFixed(decimals);
}

// ---------------------------------------------------------------------------
// PredictionResults — visual monitoring dashboard
// ---------------------------------------------------------------------------

function PredictionResults({
  response,
  inputs,
}: {
  response: CompressorEnergyResponse;
  inputs: PredictionInputs | null;
}) {
  const {
    Torque,
    T_coil,
    Pin,
    Pmech,
    MotorLoss,
    balance_error_pct,
    converged,
  } = response;

  const motorColor = getMotorColor(T_coil);
  const unaccounted = Math.max(0, Pin - Pmech - MotorLoss);
  const pctPmech = Pin > 0 ? (Pmech / Pin) * 100 : 0;
  const pctMotorLoss = Pin > 0 ? (MotorLoss / Pin) * 100 : 0;
  const pctUnaccounted = Pin > 0 ? (unaccounted / Pin) * 100 : 0;
  const isUnaccountedHigh = pctUnaccounted > 10;

  return (
    <div className="space-y-5">
      <h3 className="text-sm font-semibold text-foreground">
        Energy Balance Prediction — Monitoring Dashboard
      </h3>

      {/* Convergence badge */}
      <div
        className={`inline-flex items-center gap-1.5 rounded-md border px-3 py-1.5 text-xs font-medium ${
          converged
            ? "border-green-500/30 bg-green-500/10 text-green-700 dark:text-green-400"
            : "border-yellow-500/30 bg-yellow-500/10 text-yellow-700 dark:text-yellow-400"
        }`}
      >
        <span className="text-sm">{converged ? "✓" : "⚠"}</span>
        {converged ? "Converged" : "Did not converge"}
      </div>

      {/* ===== SVG DIAGRAM ===== */}
      <div className="w-full overflow-x-auto">
        <svg
          viewBox="0 0 620 400"
          className="w-full max-w-2xl mx-auto"
          style={{ minWidth: 400 }}
          aria-label="Hermetic compressor cross-section monitoring diagram"
          role="img"
        >
          {/* Background */}
          <rect x="0" y="0" width="620" height="400" fill="transparent" />

          {/* ---- SHELL ---- */}
          <rect
            x="170" y="30" width="280" height="340" rx="24" ry="24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2.5"
            className="text-muted-foreground/40"
          />
          {/* Shell label */}
          <text x="310" y="22" textAnchor="middle" fontSize="11" className="fill-muted-foreground" fontWeight="500">
            SHELL
          </text>

          {/* ---- MOTOR section ---- */}
          <rect
            x="200" y="60" width="220" height="120" rx="12" ry="12"
            fill={motorColor.fill}
            fillOpacity="0.18"
            stroke={motorColor.stroke}
            strokeWidth="1.5"
          />
          {/* Motor label */}
          <text x="310" y="84" textAnchor="middle" fontSize="11" fontWeight="600" className="fill-foreground">
            MOTOR
          </text>

          {/* Motor metrics */}
          <text x="230" y="106" fontSize="12" className="fill-foreground" fontWeight="500">
            {"●"} T_coil = {fmt(T_coil)} °C
          </text>
          <text x="230" y="126" fontSize="12" className="fill-foreground" fontWeight="500">
            {"●"} MotorLoss = {fmt(MotorLoss)} W
          </text>
          <text x="230" y="146" fontSize="12" className="fill-foreground" fontWeight="500">
            {"●"} RPM = {inputs ? fmt(inputs.RPM, 0) : "—"}
          </text>

          {/* Temperature warning indicator */}
          {T_coil > 120 && (
            <text x="395" y="84" fontSize="11" fill="#DC2626" fontWeight="700">
              DANGER
            </text>
          )}
          {T_coil > 80 && T_coil <= 120 && (
            <text x="395" y="84" fontSize="11" fill="#EA580C" fontWeight="700">
              WARNING
            </text>
          )}

          {/* ---- MID-POINT connector ---- */}
          <line x1="310" y1="180" x2="310" y2="220" stroke="#14B8A6" strokeWidth="2" />
          {/* Arrow head down */}
          <polygon points="310,225 305,215 315,215" fill="#14B8A6" />

          {/* Mid-point labels (right side) */}
          {inputs ? (
            <g>
              <text x="340" y="200" fontSize="11" fill="#14B8A6" fontWeight="600">
                P_mid = {fmt(inputs.P_mid)} barG
              </text>
              <text x="340" y="216" fontSize="11" fill="#14B8A6" fontWeight="600">
                T_mid = {fmt(inputs.T_mid)} °C
              </text>
            </g>
          ) : (
            <text x="340" y="208" fontSize="11" fill="#14B8A6" fontWeight="600">
              P_mid / T_mid
            </text>
          )}

          {/* ---- COMPRESSOR section ---- */}
          <rect
            x="200" y="230" width="220" height="100" rx="12" ry="12"
            fill="#6B7280"
            fillOpacity="0.15"
            stroke="#6B7280"
            strokeWidth="1.5"
          />
          <text x="310" y="268" textAnchor="middle" fontSize="11" fontWeight="600" className="fill-foreground">
            COMPRESSOR
          </text>
          <text x="310" y="290" textAnchor="middle" fontSize="12" className="fill-foreground" fontWeight="500">
            Torque = {fmt(Torque, 3)} Nm
          </text>

          {/* ---- SUCTION arrow (left, blue) ---- */}
          <defs>
            <marker id="arrowSuction" markerWidth="8" markerHeight="6" refX="8" refY="3" orient="auto">
              <polygon points="0 0, 8 3, 0 6" fill="#3B82F6" />
            </marker>
            <marker id="arrowDischarge" markerWidth="8" markerHeight="6" refX="8" refY="3" orient="auto">
              <polygon points="0 0, 8 3, 0 6" fill="#EF4444" />
            </marker>
          </defs>
          <line
            x1="50" y1="280" x2="196" y2="280"
            stroke="#3B82F6" strokeWidth="2.5" markerEnd="url(#arrowSuction)"
          />
          {/* Suction labels */}
          {inputs ? (
            <g>
              <text x="30" y="260" fontSize="11" fill="#3B82F6" fontWeight="600">
                Ps = {fmt(inputs.Ps)} barG
              </text>
              <text x="30" y="276" fontSize="11" fill="#3B82F6" fontWeight="600">
                Ts = {fmt(inputs.Ts)} °C
              </text>
              <text x="30" y="292" fontSize="11" fill="#3B82F6" fontWeight="600">
                mdot = {fmt(inputs.mdot)} kg/h
              </text>
            </g>
          ) : (
            <text x="30" y="276" fontSize="11" fill="#3B82F6" fontWeight="600">
              Suction
            </text>
          )}
          <text x="20" y="310" fontSize="10" fill="#3B82F6" fontWeight="700" letterSpacing="1">
            SUCTION
          </text>

          {/* ---- DISCHARGE arrow (right, red) ---- */}
          <line
            x1="424" y1="280" x2="570" y2="280"
            stroke="#EF4444" strokeWidth="2.5" markerEnd="url(#arrowDischarge)"
          />
          {inputs ? (
            <g>
              <text x="440" y="270" fontSize="11" fill="#EF4444" fontWeight="600">
                Pd = {fmt(inputs.Pd)} barG
              </text>
              <text x="440" y="286" fontSize="11" fill="#EF4444" fontWeight="600">
                Td_est = {fmt(response.Td_est)} °C
              </text>
            </g>
          ) : (
            <text x="440" y="276" fontSize="11" fill="#EF4444" fontWeight="600">
              Discharge
            </text>
          )}
          <text x="540" y="310" fontSize="10" fill="#EF4444" fontWeight="700" letterSpacing="1">
            DISCHARGE
          </text>

          {/* ---- RECIRCULATION arrow (curved, red dashed) ---- */}
          <defs>
            <marker id="arrowRecirc" markerWidth="8" markerHeight="6" refX="8" refY="3" orient="auto">
              <polygon points="0 0, 8 3, 0 6" fill="#F97316" />
            </marker>
          </defs>
          <path
            d="M 440 260 C 490 260, 510 170, 440 150"
            fill="none"
            stroke="#F97316"
            strokeWidth="1.8"
            strokeDasharray="5 3"
            markerEnd="url(#arrowRecirc)"
          />
          <text x="475" y="200" fontSize="10" fill="#F97316" fontWeight="600">
            Recirc
          </text>
          <text x="460" y="214" fontSize="9" fill="#F97316">
            {fmt(response.mdot_recirc * 3600, 2)} kg/h
          </text>
          <text x="460" y="226" fontSize="9" fill="#F97316">
            ({fmt(response.recirc_ratio * 100, 1)}%)
          </text>

          {/* ---- Voltage/Current indicator (bottom-left) ---- */}
          {inputs && (
            <g>
              <text x="200" y="355" fontSize="11" className="fill-muted-foreground">
                V = {fmt(inputs.V, 0)} V  |  I = {fmt(inputs.I)} A
              </text>
            </g>
          )}
        </svg>
      </div>

      {/* ===== MOTOR STATUS PANEL ===== */}
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-2">
        <StatusCard label="Input Power" value={fmt(Pin)} unit="W" />
        <StatusCard label="Mech. Power" value={fmt(Pmech)} unit="W" />
        <StatusCard label="Motor Loss" value={fmt(MotorLoss)} unit="W" />
        <StatusCard label="Torque" value={fmt(Torque, 3)} unit="Nm" />
        <StatusCard label="Td (est.)" value={fmt(response.Td_est)} unit="degC" />
        <StatusCard
          label="Recirc. Ratio"
          value={fmt(response.recirc_ratio * 100)}
          unit="%"
          warn={response.recirc_ratio > 0.15}
        />
      </div>
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-2">
        <StatusCard label="Recirc. Flow" value={fmt(response.mdot_recirc * 3600)} unit="kg/h" />
        <StatusCard
          label="Balance Err."
          value={fmt(balance_error_pct)}
          unit="%"
          warn={balance_error_pct > 5}
        />
        <StatusCard
          label="Converged"
          value={converged ? "Yes" : "No"}
          unit=""
          warn={!converged}
        />
      </div>

      {/* ===== ENERGY BALANCE BAR ===== */}
      <div className="rounded-md border border-border bg-muted/20 p-4 space-y-3">
        <h4 className="text-xs font-semibold text-foreground">Energy Balance Breakdown</h4>

        {/* Stacked bar */}
        <div className="flex h-8 rounded-md overflow-hidden border border-border text-xs font-medium">
          {/* Pmech segment */}
          <div
            className="flex items-center justify-center bg-green-500 text-white whitespace-nowrap px-1"
            style={{ width: `${Math.max(pctPmech, 2)}%` }}
            title={`Mechanical Power: ${fmt(Pmech)} W (${fmt(pctPmech)}%)`}
          >
            {pctPmech >= 8 ? `${fmt(pctPmech)}%` : ""}
          </div>
          {/* MotorLoss segment */}
          <div
            className="flex items-center justify-center bg-amber-500 text-white whitespace-nowrap px-1"
            style={{ width: `${Math.max(pctMotorLoss, 2)}%` }}
            title={`Motor Loss: ${fmt(MotorLoss)} W (${fmt(pctMotorLoss)}%)`}
          >
            {pctMotorLoss >= 8 ? `${fmt(pctMotorLoss)}%` : ""}
          </div>
          {/* Unaccounted segment */}
          <div
            className={`flex items-center justify-center whitespace-nowrap px-1 ${
              isUnaccountedHigh
                ? "bg-red-500 text-white"
                : "bg-muted text-muted-foreground"
            }`}
            style={{ width: `${Math.max(pctUnaccounted, 2)}%` }}
            title={`Unaccounted: ${fmt(unaccounted)} W (${fmt(pctUnaccounted)}%)`}
          >
            {pctUnaccounted >= 8 ? `${fmt(pctUnaccounted)}%` : ""}
          </div>
        </div>

        {/* Legend */}
        <div className="flex flex-wrap gap-4 text-xs">
          <div className="flex items-center gap-1.5">
            <span className="inline-block w-3 h-3 rounded-sm bg-green-500" />
            <span className="text-muted-foreground">Pmech: {fmt(Pmech)} W ({fmt(pctPmech)}%)</span>
          </div>
          <div className="flex items-center gap-1.5">
            <span className="inline-block w-3 h-3 rounded-sm bg-amber-500" />
            <span className="text-muted-foreground">MotorLoss: {fmt(MotorLoss)} W ({fmt(pctMotorLoss)}%)</span>
          </div>
          <div className="flex items-center gap-1.5">
            <span className={`inline-block w-3 h-3 rounded-sm ${isUnaccountedHigh ? "bg-red-500" : "bg-muted"}`} />
            <span className={`text-muted-foreground ${isUnaccountedHigh ? "dark:text-red-400" : ""}`}>
              Unaccounted: {fmt(unaccounted)} W ({fmt(pctUnaccounted)}%)
              {isUnaccountedHigh && " — high imbalance"}
            </span>
          </div>
        </div>

        {/* Total label */}
        <p className="text-xs text-muted-foreground">
          Pin = {fmt(Pin)} W (total input power)
        </p>
      </div>

      {/* ===== ALL OUTPUT PARAMETERS ===== */}
      <details className="rounded-md border border-border">
        <summary className="px-3 py-2 text-xs font-semibold text-muted-foreground cursor-pointer hover:bg-muted/50 transition-colors">
          All Output Parameters
        </summary>
        <div className="px-3 pb-3 grid grid-cols-2 sm:grid-cols-4 gap-3">
          <ParamCard label="Torque" value={Torque} unit="Nm" />
          <ParamCard label="Coil Temperature" value={T_coil} unit="degC" />
          <ParamCard label="Input Power" value={Pin} unit="W" />
          <ParamCard label="Mechanical Power" value={Pmech} unit="W" />
          <ParamCard label="Motor Loss" value={MotorLoss} unit="W" />
          <ParamCard label="Heat to Refrigerant" value={response.Q_refrig} unit="W" />
          <ParamCard label="Heat to Ambient" value={response.Q_ambient} unit="W" />
          <ParamCard label="Suction Enthalpy" value={response.hs} unit="J/kg" />
          <ParamCard label="Mid-Point Enthalpy" value={response.h_mid} unit="J/kg" />
          <ParamCard label="Discharge Enthalpy" value={response.hd} unit="J/kg" />
          <ParamCard label="Est. Discharge Temp" value={response.Td_est} unit="degC" />
          <ParamCard label="Recirc. Mass Flow" value={response.mdot_recirc} unit="kg/s" />
          <ParamCard label="Recirc. Ratio" value={response.recirc_ratio} unit="-" />
          <ParamCard label="Balance Error" value={balance_error_pct} unit="%" />
        </div>
      </details>
    </div>
  );
}

// ---------------------------------------------------------------------------
// StatusCard — small stat card for the motor status panel
// ---------------------------------------------------------------------------

function StatusCard({
  label,
  value,
  unit,
  warn = false,
}: {
  label: string;
  value: string;
  unit: string;
  warn?: boolean;
}) {
  return (
    <div
      className={`rounded-md border p-2.5 text-center ${
        warn
          ? "border-yellow-500/40 bg-yellow-500/5"
          : "border-border bg-card"
      }`}
    >
      <p className="text-[10px] text-muted-foreground uppercase tracking-wide mb-0.5">
        {label}
      </p>
      <p className="text-sm font-mono tabular-nums font-semibold">
        {value}
        {unit && (
          <span className="text-[10px] text-muted-foreground font-normal ml-1">
            {unit}
          </span>
        )}
      </p>
    </div>
  );
}

function CalibrationResults({ result }: { result: EnergyCalibResult }) {
  const {
    R_coil_case,
    R_coil_core,
    R_coil_refrigerant,
    rmse_T_coil,
    mae_T_coil,
    max_error_T_coil,
    rmse_Td,
    n_points,
    converged,
    iterations,
    T_coil_predicted,
    T_coil_measured,
    Td_predicted,
  } = result;

  const tcoilChartData = useMemo(() => {
    if (T_coil_predicted.length === 0) return null;
    const indices = T_coil_predicted.map((_, i) => i + 1);
    return { x: indices, pred: T_coil_predicted, meas: T_coil_measured };
  }, [T_coil_predicted, T_coil_measured]);

  return (
    <div className="space-y-4">
      <h3 className="text-sm font-semibold text-foreground">
        Calibration Results
      </h3>

      <div
        className={`rounded-md border px-3 py-2 text-xs ${
          converged
            ? "border-green-500/30 bg-green-500/10 text-green-700"
            : "border-yellow-500/30 bg-yellow-500/10 text-yellow-700"
        }`}
      >
        {converged
          ? `Converged — ${iterations} evaluations, ${n_points} points`
          : `Did not converge (${iterations} evaluations, ${n_points} points)`}
      </div>

      <div className="grid grid-cols-3 gap-3">
        <ParamCard label="R_coil_case" value={R_coil_case} unit="K/W" />
        <ParamCard label="R_coil_core" value={R_coil_core} unit="K/W" />
        <ParamCard label="R_coil_refrigerant" value={R_coil_refrigerant} unit="K/W" />
      </div>

      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        <MetricCard label="RMSE T_coil" value={`${rmse_T_coil.toFixed(2)} degC`} />
        <MetricCard label="MAE T_coil" value={`${mae_T_coil.toFixed(2)} degC`} />
        <MetricCard label="Max Error" value={`${max_error_T_coil.toFixed(2)} degC`} />
        {rmse_Td != null && <MetricCard label="RMSE Td" value={`${rmse_Td.toFixed(2)} degC`} />}
      </div>

      {tcoilChartData && (
        <ChartCard title="T_coil: Predicted vs Measured">
          <Plot
            data={[
              {
                x: tcoilChartData.x,
                y: tcoilChartData.meas,
                type: "scatter" as const,
                mode: "markers" as const,
                name: "Measured",
                marker: { color: "rgba(0,0,0,0.4)", size: 7 },
              },
              {
                x: tcoilChartData.x,
                y: tcoilChartData.pred,
                type: "scatter" as const,
                mode: "markers" as const,
                name: "Predicted",
                marker: { color: "hsl(217, 91%, 60%)", size: 7, symbol: "diamond" },
              },
            ]}
            layout={{
              autosize: true,
              height: 350,
              margin: { l: 50, r: 20, t: 10, b: 40 },
              xaxis: { title: { text: "Data Point" }, gridcolor: "rgba(0,0,0,0.06)" },
              yaxis: { title: { text: "T_coil [degC]" }, gridcolor: "rgba(0,0,0,0.06)" },
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
        </ChartCard>
      )}
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

function ChartCard({
  title,
  children,
}: {
  title: string;
  children: React.ReactNode;
}) {
  return (
    <div className="rounded-md border border-border bg-muted/20 p-4">
      <h4 className="text-xs font-semibold text-foreground mb-2">{title}</h4>
      {children}
    </div>
  );
}
