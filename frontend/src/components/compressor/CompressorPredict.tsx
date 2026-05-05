import { useState } from "react";
import { compressorApi } from "@/lib/api";
import type {
  CompressorEnergyResponse,
  LookupTableInput,
  LookupEntry,
} from "@/types/compressor";
import type { PredictionInputs } from "@/components/compressor/CompressorResults";
import { Button } from "@/components/ui/button";
import { Zap, ChevronDown, ChevronRight, Plus, Trash2 } from "lucide-react";

interface CompressorPredictProps {
  onResult: (result: CompressorEnergyResponse, inputs?: PredictionInputs) => void;
  torqueTable: LookupTableInput[];
  lossTable: LookupTableInput[];
  onTorqueTableChange: (tables: LookupTableInput[]) => void;
  onLossTableChange: (tables: LookupTableInput[]) => void;
}

// ---------------------------------------------------------------------------
// Field definitions
// ---------------------------------------------------------------------------
interface FieldDef {
  key: string;
  label: string;
  unit: string;
  defaultValue: number;
}

const REFRIGERANT_FIELDS: FieldDef[] = [
  { key: "Ps", label: "Suction Pressure", unit: "barG", defaultValue: 2.0 },
  { key: "Ts", label: "Suction Temperature", unit: "degC", defaultValue: 25 },
  { key: "P_mid", label: "Mid-Point Pressure", unit: "barG", defaultValue: 3.0 },
  { key: "T_mid", label: "Mid-Point Temperature", unit: "degC", defaultValue: 45 },
  { key: "Pd", label: "Discharge Pressure", unit: "barG", defaultValue: 15.0 },
  { key: "mdot", label: "Mass Flow Rate", unit: "kg/h", defaultValue: 50 },
];

const MOTOR_FIELDS: FieldDef[] = [
  { key: "V", label: "Voltage (Line-to-Line)", unit: "V", defaultValue: 380 },
  { key: "I", label: "Current", unit: "A", defaultValue: 5 },
  { key: "RPM", label: "RPM", unit: "rpm", defaultValue: 3000 },
];

const THERMAL_FIELDS: FieldDef[] = [
  { key: "R_coil_case", label: "R_coil_case", unit: "K/W", defaultValue: 0.05 },
  { key: "R_coil_core", label: "R_coil_core", unit: "K/W", defaultValue: 0.03 },
  { key: "R_coil_refrigerant", label: "R_coil_refrigerant", unit: "K/W", defaultValue: 0.02 },
  { key: "T_ambient", label: "Ambient Temperature", unit: "degC", defaultValue: 25 },
];


// ---------------------------------------------------------------------------
// Result display rows
// ---------------------------------------------------------------------------
interface ResultRow {
  key: keyof CompressorEnergyResponse;
  label: string;
  unit: string;
  format: (v: number | boolean) => string;
}

const RESULT_ROWS: ResultRow[] = [
  { key: "Torque", label: "Torque", unit: "Nm", format: (v) => v.toFixed(3) },
  { key: "T_coil", label: "Coil Temperature", unit: "degC", format: (v) => v.toFixed(2) },
  { key: "Pin", label: "Input Power", unit: "W", format: (v) => v.toFixed(1) },
  { key: "Pmech", label: "Mechanical Power", unit: "W", format: (v) => v.toFixed(1) },
  { key: "MotorLoss", label: "Motor Loss", unit: "W", format: (v) => v.toFixed(1) },
  { key: "Q_refrig", label: "Heat to Refrigerant", unit: "W", format: (v) => v.toFixed(1) },
  { key: "Q_ambient", label: "Heat to Ambient", unit: "W", format: (v) => v.toFixed(1) },
  { key: "hs", label: "Suction Enthalpy", unit: "J/kg", format: (v) => v.toFixed(2) },
  { key: "h_mid", label: "Mid-Point Enthalpy", unit: "J/kg", format: (v) => v.toFixed(2) },
  { key: "hd", label: "Discharge Enthalpy", unit: "J/kg", format: (v) => v.toFixed(2) },
  { key: "Td_est", label: "Est. Discharge Temp", unit: "degC", format: (v) => v.toFixed(2) },
  { key: "mdot_recirc", label: "Recirc. Mass Flow", unit: "kg/s", format: (v) => v.toFixed(4) },
  { key: "recirc_ratio", label: "Recirc. Ratio", unit: "-", format: (v) => (v * 100).toFixed(2) + "%" },
  { key: "balance_error_pct", label: "Energy Balance Error", unit: "%", format: (v) => v.toFixed(2) },
  { key: "converged", label: "Converged", unit: "-", format: (v) => (v ? "Yes" : "No") },
];

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------
function buildDefaults(fields: FieldDef[]): Record<string, number> {
  return Object.fromEntries(fields.map((f) => [f.key, f.defaultValue]));
}

function updateTableRpm(
  tables: LookupTableInput[],
  index: number,
  rpm: number,
): LookupTableInput[] {
  return tables.map((t, i) => (i === index ? { ...t, rpm } : t));
}

function updateEntry(
  tables: LookupTableInput[],
  tableIdx: number,
  entryIdx: number,
  field: "x" | "y",
  value: number,
): LookupTableInput[] {
  return tables.map((t, i) => {
    if (i !== tableIdx) return t;
    const entries = t.entries.map((e, j) =>
      j === entryIdx ? { ...e, [field]: value } : e,
    );
    return { ...t, entries };
  });
}

function addEntry(tables: LookupTableInput[], tableIdx: number): LookupTableInput[] {
  return tables.map((t, i) => {
    if (i !== tableIdx) return t;
    return { ...t, entries: [...t.entries, { x: 0, y: 0 }] };
  });
}

function removeEntry(
  tables: LookupTableInput[],
  tableIdx: number,
  entryIdx: number,
): LookupTableInput[] {
  return tables.map((t, i) => {
    if (i !== tableIdx) return t;
    return { ...t, entries: t.entries.filter((_, j) => j !== entryIdx) };
  });
}

function addRpmRow(tables: LookupTableInput[]): LookupTableInput[] {
  return [...tables, { rpm: 0, entries: [{ x: 0, y: 0 }] }];
}

function removeRpmRow(tables: LookupTableInput[], tableIdx: number): LookupTableInput[] {
  return tables.filter((_, i) => i !== tableIdx);
}

// ---------------------------------------------------------------------------
// Sub-component: Field group
// ---------------------------------------------------------------------------
function FieldGroup({
  title,
  fields,
  values,
  onChange,
}: {
  title: string;
  fields: FieldDef[];
  values: Record<string, number>;
  onChange: (key: string, value: number) => void;
}) {
  return (
    <div className="space-y-2">
      <h3 className="text-xs font-semibold text-muted-foreground uppercase tracking-wide">
        {title}
      </h3>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
        {fields.map((f) => (
          <div key={f.key} className="flex items-center gap-2">
            <label className="w-40 text-xs text-muted-foreground shrink-0">
              {f.label}
              <span className="text-muted-foreground/60 ml-1">[{f.unit}]</span>
            </label>
            <input
              type="number"
              step="any"
              className="w-28 rounded-md border border-input bg-background px-2 py-1.5 text-sm font-mono tabular-nums"
              value={values[f.key]}
              onChange={(e) => {
                const v = parseFloat(e.target.value);
                if (!isNaN(v)) onChange(f.key, v);
              }}
            />
          </div>
        ))}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Sub-component: Lookup table editor
// ---------------------------------------------------------------------------
function LookupTableEditor({
  title,
  xLabel,
  yLabel,
  tables,
  onTablesChange,
}: {
  title: string;
  xLabel: string;
  yLabel: string;
  tables: LookupTableInput[];
  onTablesChange: (tables: LookupTableInput[]) => void;
}) {
  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <h4 className="text-xs font-semibold text-muted-foreground">{title}</h4>
        <Button
          variant="outline"
          size="sm"
          className="h-6 text-xs"
          onClick={() => onTablesChange(addRpmRow(tables))}
        >
          <Plus className="size-3 mr-1" />
          Add RPM Row
        </Button>
      </div>

      {tables.map((table, tIdx) => (
        <div key={tIdx} className="border rounded-md p-2 space-y-2">
          <div className="flex items-center gap-2">
            <label className="text-xs text-muted-foreground w-16">RPM:</label>
            <input
              type="number"
              step="any"
              className="w-24 rounded-md border border-input bg-background px-2 py-1 text-sm font-mono tabular-nums"
              value={table.rpm}
              onChange={(e) => {
                const v = parseFloat(e.target.value);
                if (!isNaN(v)) onTablesChange(updateTableRpm(tables, tIdx, v));
              }}
            />
            <Button
              variant="ghost"
              size="sm"
              className="h-6 w-6 p-0 ml-auto text-destructive hover:text-destructive"
              onClick={() => onTablesChange(removeRpmRow(tables, tIdx))}
            >
              <Trash2 className="size-3" />
            </Button>
          </div>

          <table className="w-full text-xs">
            <thead>
              <tr className="text-muted-foreground">
                <th className="text-left font-medium w-16">{xLabel}</th>
                <th className="text-left font-medium w-16">{yLabel}</th>
                <th className="w-8" />
              </tr>
            </thead>
            <tbody>
              {table.entries.map((entry, eIdx) => (
                <tr key={eIdx}>
                  <td>
                    <input
                      type="number"
                      step="any"
                      className="w-full rounded border border-input bg-background px-1.5 py-0.5 font-mono tabular-nums"
                      value={entry.x}
                      onChange={(e) => {
                        const v = parseFloat(e.target.value);
                        if (!isNaN(v))
                          onTablesChange(updateEntry(tables, tIdx, eIdx, "x", v));
                      }}
                    />
                  </td>
                  <td>
                    <input
                      type="number"
                      step="any"
                      className="w-full rounded border border-input bg-background px-1.5 py-0.5 font-mono tabular-nums"
                      value={entry.y}
                      onChange={(e) => {
                        const v = parseFloat(e.target.value);
                        if (!isNaN(v))
                          onTablesChange(updateEntry(tables, tIdx, eIdx, "y", v));
                      }}
                    />
                  </td>
                  <td>
                    <Button
                      variant="ghost"
                      size="sm"
                      className="h-5 w-5 p-0 text-destructive hover:text-destructive"
                      onClick={() =>
                        onTablesChange(removeEntry(tables, tIdx, eIdx))
                      }
                    >
                      <Trash2 className="size-2.5" />
                    </Button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>

          <Button
            variant="outline"
            size="sm"
            className="h-5 text-xs"
            onClick={() => onTablesChange(addEntry(tables, tIdx))}
          >
            <Plus className="size-2.5 mr-1" />
            Add Entry
          </Button>
        </div>
      ))}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Sub-component: Results card
// ---------------------------------------------------------------------------
function ResultsCard({ result }: { result: CompressorEnergyResponse }) {
  return (
    <div className="rounded-md border bg-card p-4 space-y-2">
      <h3 className="text-sm font-semibold">Prediction Results</h3>
      <table className="w-full text-sm">
        <thead>
          <tr className="text-muted-foreground text-xs">
            <th className="text-left font-medium">Output</th>
            <th className="text-right font-medium">Value</th>
            <th className="text-right font-medium">Unit</th>
          </tr>
        </thead>
        <tbody>
          {RESULT_ROWS.map((row) => {
            const val = result[row.key];
            return (
              <tr key={row.key} className="border-t border-border/50">
                <td className="py-1.5 text-muted-foreground">{row.label}</td>
                <td className="py-1.5 text-right font-mono tabular-nums">
                  {row.format(val as number & boolean)}
                </td>
                <td className="py-1.5 text-right text-muted-foreground text-xs">
                  {row.unit}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------
export default function CompressorPredict({ onResult, torqueTable, lossTable, onTorqueTableChange, onLossTableChange }: CompressorPredictProps) {
  // Scalar field values
  const [refrigerant, setRefrigerant] = useState<Record<string, number>>(
    buildDefaults(REFRIGERANT_FIELDS),
  );
  const [motor, setMotor] = useState<Record<string, number>>(
    buildDefaults(MOTOR_FIELDS),
  );
  const [thermal, setThermal] = useState<Record<string, number>>(
    buildDefaults(THERMAL_FIELDS),
  );

  // UI state
  const [tablesOpen, setTablesOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<CompressorEnergyResponse | null>(null);

  function updateScalar(
    setter: React.Dispatch<React.SetStateAction<Record<string, number>>>,
  ) {
    return (key: string, value: number) =>
      setter((prev) => ({ ...prev, [key]: value }));
  }

  async function handlePredict() {
    setLoading(true);
    setError(null);
    try {
      const res = await compressorApi.predictEnergy({
        Ps: refrigerant.Ps,
        Ts: refrigerant.Ts,
        P_mid: refrigerant.P_mid,
        T_mid: refrigerant.T_mid,
        Pd: refrigerant.Pd,
        mdot: refrigerant.mdot,
        V: motor.V,
        I: motor.I,
        RPM: motor.RPM,
        torque_table: torqueTable,
        loss_table: lossTable,
        R_coil_case: thermal.R_coil_case,
        R_coil_core: thermal.R_coil_core,
        R_coil_refrigerant: thermal.R_coil_refrigerant,
        T_ambient: thermal.T_ambient,
      });
      setResult(res);
      onResult(res, {
        Ps: refrigerant.Ps,
        Ts: refrigerant.Ts,
        P_mid: refrigerant.P_mid,
        T_mid: refrigerant.T_mid,
        Pd: refrigerant.Pd,
        mdot: refrigerant.mdot,
        V: motor.V,
        I: motor.I,
        RPM: motor.RPM,
      });
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Prediction failed");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="space-y-5">
      <h2 className="text-sm font-semibold">Energy Balance Prediction</h2>

      {/* Section 1: Refrigerant Operating Conditions */}
      <FieldGroup
        title="Refrigerant Operating Conditions"
        fields={REFRIGERANT_FIELDS}
        values={refrigerant}
        onChange={updateScalar(setRefrigerant)}
      />

      {/* Section 2: Motor Electrical */}
      <FieldGroup
        title="Motor Electrical"
        fields={MOTOR_FIELDS}
        values={motor}
        onChange={updateScalar(setMotor)}
      />

      {/* Section 3: Thermal Parameters */}
      <FieldGroup
        title="Thermal Parameters"
        fields={THERMAL_FIELDS}
        values={thermal}
        onChange={updateScalar(setThermal)}
      />

      {/* Section 4: Lookup Tables (collapsible) */}
      <div className="rounded-md border">
        <button
          type="button"
          className="flex items-center gap-2 w-full px-3 py-2 text-left text-xs font-semibold text-muted-foreground uppercase tracking-wide hover:bg-muted/50 transition-colors"
          onClick={() => setTablesOpen((prev) => !prev)}
        >
          {tablesOpen ? (
            <ChevronDown className="size-3.5" />
          ) : (
            <ChevronRight className="size-3.5" />
          )}
          Lookup Tables
        </button>

        {tablesOpen && (
          <div className="px-3 pb-3 space-y-4">
            <LookupTableEditor
              title="I-Torque Table"
              xLabel="I (A)"
              yLabel="Torque (Nm)"
              tables={torqueTable}
              onTablesChange={onTorqueTableChange}
            />
            <LookupTableEditor
              title="Loss Table"
              xLabel="Torque (Nm)"
              yLabel="Loss (W)"
              tables={lossTable}
              onTablesChange={onLossTableChange}
            />
          </div>
        )}
      </div>

      {/* Run button */}
      <Button onClick={() => void handlePredict()} disabled={loading}>
        <Zap className="size-3.5 mr-1" />
        {loading ? "Predicting..." : "Run Energy Prediction"}
      </Button>

      {/* Error */}
      {error && (
        <div className="rounded-md border border-destructive/50 bg-destructive/10 px-3 py-2">
          <p className="text-xs text-destructive">{error}</p>
        </div>
      )}

      {/* Results */}
      {result && <ResultsCard result={result} />}
    </div>
  );
}
