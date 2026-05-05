import { useState, useCallback } from "react";
import { compressorApi } from "@/lib/api";
import type {
  CalibDataPoint,
  EnergyCalibResult,
  LookupTableInput,
} from "@/types/compressor";
import { Button } from "@/components/ui/button";
import { FlaskConical, Plus, Trash2, Upload } from "lucide-react";

interface FieldDef {
  key: keyof CalibDataPoint;
  label: string;
  unit: string;
  defaultValue: number;
}

const REQUIRED_FIELDS: FieldDef[] = [
  { key: "Ps", label: "Ps", unit: "barG", defaultValue: 2.0 },
  { key: "Ts", label: "Ts", unit: "degC", defaultValue: 25 },
  { key: "P_mid", label: "P_mid", unit: "barG", defaultValue: 3.0 },
  { key: "T_mid", label: "T_mid", unit: "degC", defaultValue: 45 },
  { key: "Pd", label: "Pd", unit: "barG", defaultValue: 15.0 },
  { key: "mdot", label: "mdot", unit: "kg/h", defaultValue: 50 },
  { key: "V", label: "Voltage", unit: "V", defaultValue: 380 },
  { key: "I", label: "Current", unit: "A", defaultValue: 5 },
  { key: "RPM", label: "RPM", unit: "rpm", defaultValue: 3000 },
  { key: "T_coil_measured", label: "T_coil (meas)", unit: "degC", defaultValue: 80 },
];

const OPTIONAL_FIELDS: FieldDef[] = [
  { key: "Td_measured", label: "Td (meas)", unit: "degC", defaultValue: 0 },
];

const ALL_FIELDS = [...REQUIRED_FIELDS, ...OPTIONAL_FIELDS];

interface CompressorCalibrateProps {
  torqueTable: LookupTableInput[];
  lossTable: LookupTableInput[];
  onResult: (result: EnergyCalibResult) => void;
}

function buildEmptyRow(): Record<string, number> {
  const row: Record<string, number> = {};
  for (const f of ALL_FIELDS) {
    row[f.key] = f.defaultValue;
  }
  return row;
}

export default function CompressorCalibrate({
  torqueTable,
  lossTable,
  onResult,
}: CompressorCalibrateProps) {
  const [rows, setRows] = useState<Record<string, number>[]>([
    buildEmptyRow(),
    buildEmptyRow(),
    buildEmptyRow(),
  ]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<EnergyCalibResult | null>(null);

  const updateCell = useCallback(
    (rowIdx: number, key: string, value: number) => {
      setRows((prev) =>
        prev.map((r, i) => (i === rowIdx ? { ...r, [key]: value } : r)),
      );
    },
    [],
  );

  const addRow = useCallback(() => {
    setRows((prev) => [...prev, buildEmptyRow()]);
  }, []);

  const removeRow = useCallback((idx: number) => {
    setRows((prev) => prev.filter((_, i) => i !== idx));
  }, []);

  const handleCSVImport = useCallback(() => {
    const input = document.createElement("input");
    input.type = "file";
    input.accept = ".csv";
    input.onchange = (e) => {
      const file = (e.target as HTMLInputElement).files?.[0];
      if (!file) return;
      const reader = new FileReader();
      reader.onload = (ev) => {
        const text = ev.target?.result as string;
        const lines = text.trim().split("\n");
        if (lines.length < 2) return;
        const headers = lines[0].split(",").map((h) => h.trim());
        const parsed: Record<string, number>[] = [];
        for (let i = 1; i < lines.length; i++) {
          const vals = lines[i].split(",").map((v) => v.trim());
          const row: Record<string, number> = {};
          for (const f of ALL_FIELDS) {
            const idx = headers.indexOf(f.key);
            row[f.key] = idx >= 0 ? parseFloat(vals[idx]) || f.defaultValue : f.defaultValue;
          }
          parsed.push(row);
        }
        setRows(parsed.length > 0 ? parsed : [buildEmptyRow()]);
      };
      reader.readAsText(file);
    };
    input.click();
  }, []);

  async function handleCalibrate() {
    setLoading(true);
    setError(null);
    try {
      const dataPoints: CalibDataPoint[] = rows.map((r) => ({
        Ps: r.Ps,
        Ts: r.Ts,
        P_mid: r.P_mid,
        T_mid: r.T_mid,
        Pd: r.Pd,
        mdot: r.mdot,
        V: r.V,
        I: r.I,
        RPM: r.RPM,
        T_coil_measured: r.T_coil_measured,
        Td_measured: r.Td_measured || null,
      }));

      const res = await compressorApi.calibrateEnergy({
        data_points: dataPoints,
        torque_table: torqueTable,
        loss_table: lossTable,
      });
      setResult(res);
      onResult(res);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Calibration failed");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="space-y-5">
      <div className="flex items-center justify-between">
        <h2 className="text-sm font-semibold">Calibrate Thermal Resistances</h2>
        <div className="flex gap-2">
          <Button variant="outline" size="sm" className="h-7 text-xs" onClick={handleCSVImport}>
            <Upload className="size-3 mr-1" />
            Import CSV
          </Button>
          <Button variant="outline" size="sm" className="h-7 text-xs" onClick={addRow}>
            <Plus className="size-3 mr-1" />
            Add Row
          </Button>
        </div>
      </div>

      <p className="text-xs text-muted-foreground">
        Enter measurement data points (operating conditions + measured T_coil).
        Uses the same lookup tables from the Predict tab. Minimum 3 points required.
      </p>

      {/* Data table */}
      <div className="overflow-x-auto">
        <table className="w-full text-xs border-collapse">
          <thead>
            <tr className="text-muted-foreground">
              {REQUIRED_FIELDS.map((f) => (
                <th key={f.key} className="text-left font-medium px-1 py-1 whitespace-nowrap">
                  {f.label}
                  <span className="text-muted-foreground/60 ml-0.5">[{f.unit}]</span>
                </th>
              ))}
              {OPTIONAL_FIELDS.map((f) => (
                <th key={f.key} className="text-left font-medium px-1 py-1 whitespace-nowrap opacity-60">
                  {f.label}
                  <span className="ml-0.5">[{f.unit}]</span>
                </th>
              ))}
              <th className="w-8" />
            </tr>
          </thead>
          <tbody>
            {rows.map((row, rIdx) => (
              <tr key={rIdx} className="border-t border-border/30">
                {ALL_FIELDS.map((f) => (
                  <td key={f.key} className="px-0.5 py-0.5">
                    <input
                      type="number"
                      step="any"
                      className="w-20 rounded border border-input bg-background px-1.5 py-1 font-mono tabular-nums"
                      value={row[f.key]}
                      onChange={(e) => {
                        const v = parseFloat(e.target.value);
                        if (!isNaN(v)) updateCell(rIdx, f.key, v);
                      }}
                    />
                  </td>
                ))}
                <td>
                  {rows.length > 1 && (
                    <Button
                      variant="ghost"
                      size="sm"
                      className="h-6 w-6 p-0 text-destructive hover:text-destructive"
                      onClick={() => removeRow(rIdx)}
                    >
                      <Trash2 className="size-3" />
                    </Button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Run button */}
      <Button onClick={() => void handleCalibrate()} disabled={loading || rows.length < 3}>
        <FlaskConical className="size-3.5 mr-1" />
        {loading ? "Calibrating..." : `Run Calibration (${rows.length} points)`}
      </Button>

      {rows.length < 3 && (
        <p className="text-xs text-yellow-600">Minimum 3 data points required for calibration.</p>
      )}

      {/* Error */}
      {error && (
        <div className="rounded-md border border-destructive/50 bg-destructive/10 px-3 py-2">
          <p className="text-xs text-destructive">{error}</p>
        </div>
      )}

      {/* Results */}
      {result && <CalibResultCard result={result} />}
    </div>
  );
}

function fmt(v: number, decimals = 4): string {
  return v.toFixed(decimals);
}

function CalibResultCard({ result }: { result: EnergyCalibResult }) {
  return (
    <div className="space-y-4">
      <div
        className={`inline-flex items-center gap-1.5 rounded-md border px-3 py-1.5 text-xs font-medium ${
          result.converged
            ? "border-green-500/30 bg-green-500/10 text-green-700 dark:text-green-400"
            : "border-yellow-500/30 bg-yellow-500/10 text-yellow-700 dark:text-yellow-400"
        }`}
      >
        <span className="text-sm">{result.converged ? "✓" : "⚠"}</span>
        {result.converged ? "Converged" : "Did not converge"} — {result.iterations} evaluations, {result.n_points} points
      </div>

      {/* Calibrated R values */}
      <div className="grid grid-cols-3 gap-3">
        <div className="rounded-md border border-border bg-card p-3">
          <p className="text-xs text-muted-foreground">R_coil_case</p>
          <p className="text-lg font-mono tabular-nums font-semibold">{fmt(result.R_coil_case)}</p>
          <p className="text-xs text-muted-foreground">K/W</p>
        </div>
        <div className="rounded-md border border-border bg-card p-3">
          <p className="text-xs text-muted-foreground">R_coil_core</p>
          <p className="text-lg font-mono tabular-nums font-semibold">{fmt(result.R_coil_core)}</p>
          <p className="text-xs text-muted-foreground">K/W</p>
        </div>
        <div className="rounded-md border border-border bg-card p-3">
          <p className="text-xs text-muted-foreground">R_coil_refrigerant</p>
          <p className="text-lg font-mono tabular-nums font-semibold">{fmt(result.R_coil_refrigerant)}</p>
          <p className="text-xs text-muted-foreground">K/W</p>
        </div>
      </div>

      {/* Error metrics */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
        <div className="rounded-md border border-border bg-card p-2.5 text-center">
          <p className="text-[10px] text-muted-foreground uppercase">RMSE T_coil</p>
          <p className="text-sm font-mono tabular-nums font-semibold">{fmt(result.rmse_T_coil, 2)} degC</p>
        </div>
        <div className="rounded-md border border-border bg-card p-2.5 text-center">
          <p className="text-[10px] text-muted-foreground uppercase">MAE T_coil</p>
          <p className="text-sm font-mono tabular-nums font-semibold">{fmt(result.mae_T_coil, 2)} degC</p>
        </div>
        <div className="rounded-md border border-border bg-card p-2.5 text-center">
          <p className="text-[10px] text-muted-foreground uppercase">Max Error</p>
          <p className="text-sm font-mono tabular-nums font-semibold">{fmt(result.max_error_T_coil, 2)} degC</p>
        </div>
        {result.rmse_Td != null && (
          <div className="rounded-md border border-border bg-card p-2.5 text-center">
            <p className="text-[10px] text-muted-foreground uppercase">RMSE Td</p>
            <p className="text-sm font-mono tabular-nums font-semibold">{fmt(result.rmse_Td, 2)} degC</p>
          </div>
        )}
      </div>

      {/* Per-point comparison */}
      <details className="rounded-md border border-border" open>
        <summary className="px-3 py-2 text-xs font-semibold text-muted-foreground cursor-pointer hover:bg-muted/50">
          Per-Point Comparison ({result.n_points} points)
        </summary>
        <div className="px-3 pb-3">
          <table className="w-full text-xs">
            <thead>
              <tr className="text-muted-foreground">
                <th className="text-left font-medium px-2 py-1">#</th>
                <th className="text-right font-medium px-2 py-1">T_coil Pred</th>
                <th className="text-right font-medium px-2 py-1">T_coil Meas</th>
                <th className="text-right font-medium px-2 py-1">Error</th>
                <th className="text-right font-medium px-2 py-1">Td Pred</th>
              </tr>
            </thead>
            <tbody>
              {result.T_coil_predicted.map((pred, i) => {
                const meas = result.T_coil_measured[i];
                const err = pred - meas;
                return (
                  <tr key={i} className="border-t border-border/30">
                    <td className="px-2 py-1 text-muted-foreground">{i + 1}</td>
                    <td className="px-2 py-1 text-right font-mono">{pred.toFixed(2)}</td>
                    <td className="px-2 py-1 text-right font-mono">{meas.toFixed(2)}</td>
                    <td className={`px-2 py-1 text-right font-mono ${Math.abs(err) > 5 ? "text-destructive" : ""}`}>
                      {err > 0 ? "+" : ""}{err.toFixed(2)}
                    </td>
                    <td className="px-2 py-1 text-right font-mono">
                      {(result.Td_predicted[i] ?? 0).toFixed(2)}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </details>
    </div>
  );
}
