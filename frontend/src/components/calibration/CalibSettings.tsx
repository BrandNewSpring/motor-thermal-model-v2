import { useState } from "react";
import type { CalibSettings as CalibSettingsType } from "@/types/calibration";
import { filesApi } from "@/lib/api";

type Mapping = Record<string, string | undefined>;

interface CalibSettingsProps {
  settings: CalibSettingsType;
  onSettingsChange: (settings: CalibSettingsType) => void;
  columns: string[];
  columnMapping: Mapping;
  onColumnMappingChange: (mapping: Mapping) => void;
  fileId: string | null;
}

const COL_LABELS: Record<string, string> = {
  time: "Time",
  rpm: "RPM",
  I_phase: "I phase",
  T_amb: "T ambient",
  T_coil: "T coil",
  torque: "Torque",
};
const COL_HINTS: Record<string, string> = {
  time: "Elapsed seconds",
  rpm: "Motor speed [/min]",
  I_phase: "Phase current [A]",
  T_amb: "Ambient/chamber temp",
  T_coil: "Coil/winding temp",
  torque: "Torque [Nm]",
};
const REQUIRED_COLS = ["I_phase", "T_amb", "T_coil"];
const OPTIONAL_COLS = ["time", "rpm", "torque"];
const ALL_COLS = [...REQUIRED_COLS, ...OPTIONAL_COLS];

export default function CalibSettingsForm({
  settings,
  onSettingsChange,
  columns,
  columnMapping,
  onColumnMappingChange,
  fileId,
}: CalibSettingsProps) {
  const [advancedOpen, setAdvancedOpen] = useState(false);
  const [mappingStatus, setMappingStatus] = useState<string | null>(null);

  async function handleMapColumns() {
    if (!fileId) return;
    try {
      const result = await filesApi.mapColumns(fileId, {
        time: columnMapping["time"] ?? null,
        rpm: columnMapping["rpm"] ?? null,
        I_phase: columnMapping["I_phase"] ?? "",
        T_amb: columnMapping["T_amb"] ?? "",
        T_coil: columnMapping["T_coil"] ?? "",
        torque: columnMapping["torque"] ?? null,
      });
      setMappingStatus(`Mapped ${result.mapped_rows} rows successfully`);
    } catch (err: unknown) {
      setMappingStatus(
        err instanceof Error ? err.message : "Column mapping failed",
      );
    }
  }

  function updateSetting<K extends keyof CalibSettingsType>(
    key: K,
    value: CalibSettingsType[K],
  ) {
    // Guard: reject NaN for numeric fields to prevent 422 from backend gt=0 constraints
    if (typeof value === "number" && Number.isNaN(value)) {
      return;
    }
    onSettingsChange({ ...settings, [key]: value });
  }

  return (
    <div className="space-y-6">
      {/* Column Mapping */}
      {columns.length > 0 && (
        <div className="space-y-3">
          <h3 className="text-sm font-semibold text-foreground">
            Column Mapping
          </h3>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            {ALL_COLS.map((field) => (
              <div key={field} className="flex items-center gap-2">
                <label className="w-20 text-xs text-muted-foreground shrink-0" title={COL_HINTS[field]}>
                  {COL_LABELS[field] ?? field}
                  {REQUIRED_COLS.includes(field) && (
                    <span className="text-destructive">*</span>
                  )}
                </label>
                <select
                  className="flex-1 rounded-md border border-input bg-background px-2 py-1 text-sm"
                  value={columnMapping[field] ?? ""}
                  onChange={(e) =>
                    onColumnMappingChange({
                      ...columnMapping,
                      [field]: e.target.value || undefined,
                    })
                  }
                >
                  <option value="">-- Select --</option>
                  {columns.map((col) => (
                    <option key={col} value={col}>
                      {col}
                    </option>
                  ))}
                </select>
              </div>
            ))}
          </div>
          <button
            type="button"
            disabled={
              !columnMapping["I_phase"] ||
              !columnMapping["T_amb"] ||
              !columnMapping["T_coil"]
            }
            onClick={() => void handleMapColumns()}
            className="inline-flex items-center justify-center rounded-md border border-input bg-background px-3 py-1 text-xs font-medium transition-colors hover:bg-muted disabled:pointer-events-none disabled:opacity-50 h-7"
          >
            Validate Mapping
          </button>
          {mappingStatus && (
            <p className="text-xs text-muted-foreground">{mappingStatus}</p>
          )}
        </div>
      )}

      {/* Calibration Settings */}
      <div className="space-y-3">
        <h3 className="text-sm font-semibold text-foreground">
          Optimization Settings
        </h3>

        <div className="flex items-center gap-3">
          <label className="w-28 text-xs text-muted-foreground">
            Multi-starts
          </label>
          <input
            type="range"
            min={1}
            max={20}
            value={settings.n_starts}
            onChange={(e) =>
              updateSetting("n_starts", parseInt(e.target.value))
            }
            className="flex-1"
          />
          <span className="text-sm font-mono tabular-nums w-6 text-right">
            {settings.n_starts}
          </span>
        </div>

        <div className="flex items-center gap-3">
          <label className="w-28 text-xs text-muted-foreground">
            Tail gamma
          </label>
          <input
            type="number"
            step="0.1"
            className="w-24 rounded-md border border-input bg-background px-2 py-1 text-sm font-mono tabular-nums"
            value={settings.tail_gamma}
            onChange={(e) =>
              updateSetting("tail_gamma", parseFloat(e.target.value))
            }
          />
        </div>

        <div className="flex items-center gap-3">
          <label className="w-28 text-xs text-muted-foreground">
            SS Penalty
          </label>
          <input
            type="number"
            step="0.5"
            className="w-24 rounded-md border border-input bg-background px-2 py-1 text-sm font-mono tabular-nums"
            value={settings.ss_penalty}
            onChange={(e) =>
              updateSetting("ss_penalty", parseFloat(e.target.value))
            }
          />
        </div>

        {/* Advanced toggle */}
        <button
          type="button"
          className="text-xs text-primary underline"
          onClick={() => setAdvancedOpen(!advancedOpen)}
        >
          {advancedOpen ? "Hide" : "Show"} Advanced Settings
        </button>

        {advancedOpen && (
          <div className="space-y-2 rounded-md border border-border bg-muted/30 p-3">
            <div className="grid grid-cols-2 gap-3">
              <div className="flex items-center gap-2">
                <label className="text-xs text-muted-foreground w-16">
                  R1_init
                </label>
                <input
                  type="number"
                  step="any"
                  placeholder="auto"
                  className="w-24 rounded-md border border-input bg-background px-2 py-1 text-xs font-mono tabular-nums"
                  value={settings.R1_init ?? ""}
                  onChange={(e) => {
                    const v = parseFloat(e.target.value);
                    updateSetting(
                      "R1_init",
                      e.target.value && v > 0 ? v : null,
                    );
                  }}
                />
              </div>
              <div className="flex items-center gap-2">
                <label className="text-xs text-muted-foreground w-16">
                  R2_init
                </label>
                <input
                  type="number"
                  step="any"
                  placeholder="auto"
                  className="w-24 rounded-md border border-input bg-background px-2 py-1 text-xs font-mono tabular-nums"
                  value={settings.R2_init ?? ""}
                  onChange={(e) => {
                    const v = parseFloat(e.target.value);
                    updateSetting(
                      "R2_init",
                      e.target.value && v > 0 ? v : null,
                    );
                  }
                  }
                />
              </div>
              <div className="flex items-center gap-2">
                <label className="text-xs text-muted-foreground w-16">
                  h_nat
                </label>
                <input
                  type="number"
                  step="any"
                  className="w-24 rounded-md border border-input bg-background px-2 py-1 text-xs font-mono tabular-nums"
                  value={settings.h_nat_init}
                  onChange={(e) =>
                    updateSetting("h_nat_init", parseFloat(e.target.value))
                  }
                />
              </div>
              <div className="flex items-center gap-2">
                <label className="text-xs text-muted-foreground w-16">
                  h_rpm
                </label>
                <input
                  type="number"
                  step="any"
                  className="w-24 rounded-md border border-input bg-background px-2 py-1 text-xs font-mono tabular-nums"
                  value={settings.h_rpm_init}
                  onChange={(e) =>
                    updateSetting("h_rpm_init", parseFloat(e.target.value))
                  }
                />
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
