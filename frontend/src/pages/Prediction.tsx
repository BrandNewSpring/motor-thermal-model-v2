import { useState, useEffect } from "react";
import { predictionApi, profilesApi } from "@/lib/api";
import type { MotorProfileSummary } from "@/types/motor";
import type { SteadyStateResult, GridPredictionResult } from "@/types/data";
import { useAppStore } from "@/stores/appStore";

export default function Prediction() {
  const { currentProfileId, setCurrentProfile } = useAppStore();

  const [profiles, setProfiles] = useState<MotorProfileSummary[]>([]);
  const [selectedId, setSelectedId] = useState(currentProfileId);

  // Single-point state
  const [I_phase, setIPhase] = useState(5);
  const [rpm, setRpm] = useState(3000);
  const [tAmb, setTAmb] = useState(25);
  const [ssResult, setSsResult] = useState<SteadyStateResult | null>(null);
  const [ssLoading, setSsLoading] = useState(false);
  const [ssError, setSsError] = useState<string | null>(null);

  // Grid state
  const [iMin, setIMin] = useState(1);
  const [iMax, setIMax] = useState(10);
  const [rpmMin, setRpmMin] = useState(0);
  const [rpmMax, setRpmMax] = useState(5000);
  const [gridResult, setGridResult] = useState<GridPredictionResult | null>(null);
  const [gridLoading, setGridLoading] = useState(false);
  const [gridError, setGridError] = useState<string | null>(null);

  useEffect(() => {
    void (async () => {
      try {
        const list = await profilesApi.list();
        setProfiles(list);
      } catch {
        // Empty list on error
      }
    })();
  }, []);

  useEffect(() => {
    if (selectedId) setCurrentProfile(selectedId);
  }, [selectedId, setCurrentProfile]);

  async function handleSteadyState() {
    if (!selectedId) return;
    setSsLoading(true);
    setSsError(null);
    try {
      const result = await predictionApi.steadyState({
        profile_id: selectedId,
        I_phase,
        T_amb: tAmb,
        rpm,
      });
      setSsResult(result);
    } catch (err: unknown) {
      setSsError(err instanceof Error ? err.message : "Prediction failed");
    } finally {
      setSsLoading(false);
    }
  }

  async function handleGrid() {
    if (!selectedId) return;
    setGridLoading(true);
    setGridError(null);
    try {
      const result = await predictionApi.grid({
        profile_id: selectedId,
        I_range: [iMin, iMax],
        RPM_range: [rpmMin, rpmMax],
        T_amb: tAmb,
        n_points: 20,
      });
      setGridResult(result);
    } catch (err: unknown) {
      setGridError(err instanceof Error ? err.message : "Grid prediction failed");
    } finally {
      setGridLoading(false);
    }
  }

  return (
    <div className="p-6 max-w-5xl mx-auto space-y-8">
      <h1 className="text-lg font-semibold">Prediction</h1>

      {/* Profile selector */}
      <div className="space-y-1">
        <label className="text-xs text-muted-foreground">
          Select Profile
        </label>
        <select
          className="w-full max-w-sm rounded-md border border-input bg-background px-3 py-2 text-sm"
          value={selectedId ?? ""}
          onChange={(e) => setSelectedId(e.target.value || null)}
        >
          <option value="">-- Select a profile --</option>
          {profiles.map((p) => (
            <option key={p.id} value={p.id}>
              {p.name}
            </option>
          ))}
        </select>
      </div>

      {!selectedId ? (
        <p className="text-sm text-muted-foreground">
          Select a profile to run predictions.
        </p>
      ) : (
        <>
          {/* Single-point prediction */}
          <section className="space-y-4">
            <h2 className="text-sm font-semibold">Steady-State Prediction</h2>
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
              <NumberInput label="I_phase [A]" value={I_phase} onChange={setIPhase} />
              <NumberInput label="RPM" value={rpm} onChange={setRpm} />
              <NumberInput label="T_amb [degC]" value={tAmb} onChange={setTAmb} />
            </div>
            <button
              type="button"
              className="inline-flex items-center justify-center rounded-md bg-primary text-primary-foreground px-4 py-1.5 text-sm font-medium hover:bg-primary/80 disabled:opacity-50"
              disabled={ssLoading}
              onClick={() => void handleSteadyState()}
            >
              {ssLoading ? "Computing..." : "Predict"}
            </button>

            {ssError && (
              <p className="text-xs text-destructive">{ssError}</p>
            )}

            {ssResult && (
              <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
                <ResultCard label="T_coil_ss" value={ssResult.T_coil_ss} unit="degC" color="blue" />
                <ResultCard label="T_core_ss" value={ssResult.T_core_ss} unit="degC" color="green" />
                <ResultCard label="T_housing_ss" value={ssResult.T_housing_ss} unit="degC" color="orange" />
                <ResultCard label="Q_copper" value={ssResult.Q_copper} unit="W" color="blue" />
                <ResultCard label="Q_iron" value={ssResult.Q_iron} unit="W" color="red" />
                <ResultCard label="R3_at_rpm" value={ssResult.R3_at_rpm} unit="degC/W" color="gray" />
              </div>
            )}
          </section>

          {/* Grid prediction */}
          <section className="space-y-4">
            <h2 className="text-sm font-semibold">Grid Heatmap</h2>
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
              <NumberInput label="I_min [A]" value={iMin} onChange={setIMin} />
              <NumberInput label="I_max [A]" value={iMax} onChange={setIMax} />
              <NumberInput label="RPM_min" value={rpmMin} onChange={setRpmMin} />
              <NumberInput label="RPM_max" value={rpmMax} onChange={setRpmMax} />
            </div>
            <button
              type="button"
              className="inline-flex items-center justify-center rounded-md bg-primary text-primary-foreground px-4 py-1.5 text-sm font-medium hover:bg-primary/80 disabled:opacity-50"
              disabled={gridLoading}
              onClick={() => void handleGrid()}
            >
              {gridLoading ? "Computing..." : "Generate Heatmap"}
            </button>

            {gridError && (
              <p className="text-xs text-destructive">{gridError}</p>
            )}

            {gridResult && (
              <div className="rounded-md border border-border bg-muted/20 p-4">
                <h4 className="text-xs font-semibold text-foreground mb-2">
                  T_coil Steady-State Heatmap (I vs RPM)
                </h4>
                <div
                  data-chart="heatmap"
                  data-grid-t-coil={JSON.stringify(gridResult.grid_T_coil)}
                  data-grid-i={JSON.stringify(gridResult.grid_I)}
                  data-grid-rpm={JSON.stringify(gridResult.grid_RPM)}
                  className="w-full h-64 bg-background rounded flex items-center justify-center text-xs text-muted-foreground"
                >
                  Heatmap renders at runtime (Plotly)
                </div>
              </div>
            )}
          </section>
        </>
      )}
    </div>
  );
}

function NumberInput({
  label,
  value,
  onChange,
}: {
  label: string;
  value: number;
  onChange: (v: number) => void;
}) {
  return (
    <div className="space-y-1">
      <label className="text-xs text-muted-foreground">{label}</label>
      <input
        type="number"
        step="any"
        className="w-full rounded-md border border-input bg-background px-2 py-1.5 text-sm font-mono tabular-nums"
        value={value}
        onChange={(e) => onChange(parseFloat(e.target.value) || 0)}
      />
    </div>
  );
}

function ResultCard({
  label,
  value,
  unit,
  color,
}: {
  label: string;
  value: number;
  unit: string;
  color: string;
}) {
  const colorMap: Record<string, string> = {
    blue: "border-blue-500/30",
    green: "border-green-500/30",
    orange: "border-orange-500/30",
    red: "border-red-500/30",
    gray: "border-border",
  };
  return (
    <div className={`rounded-md border bg-card p-2.5 ${colorMap[color] ?? "border-border"}`}>
      <p className="text-xs text-muted-foreground">{label}</p>
      <p className="text-base font-mono tabular-nums font-semibold">
        {value.toFixed(2)}
      </p>
      <p className="text-xs text-muted-foreground">{unit}</p>
    </div>
  );
}
