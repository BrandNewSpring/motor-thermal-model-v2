import { useState, useEffect, useCallback } from "react";
import { useAppStore } from "@/stores/appStore";
import { profilesApi, calibrationApi, filesApi } from "@/lib/api";
import type { MotorProfile, MotorGeometry, MaterialProps } from "@/types/motor";
import type { CalibSettings as CalibSettingsType, CalibProgressEvent } from "@/types/calibration";
import type { FileUploadResponse } from "@/types/data";
import DataUpload from "@/components/calibration/DataUpload";
import CalibSettingsForm from "@/components/calibration/CalibSettings";
import CalibProgress from "@/components/calibration/CalibProgress";
import CalibResults from "@/components/calibration/CalibResults";
import MotorForm from "@/components/motor/MotorForm";
import { Button } from "@/components/ui/button";

const STEPS = ["Data File", "Motor Profile", "Loss Model", "Calibrate"] as const;

const DEFAULT_GEOMETRY: MotorGeometry = {
  D_motor_mm: 106,
  L_motor_mm: 48.85,
  m_motor_g: 2800,
  t_housing_mm: 10.5,
  L_housing_mm: null,
  m_housing_g: 600,
  t_mold_mm: 0.5,
  f_copper: 0.35,
};

const DEFAULT_MATERIAL: MaterialProps = {
  c_p_Cu: 385,
  c_p_FeSi: 490,
  c_p_Al: 900,
  k_mold: 0.3,
  beta_iron: 0.002,
};

const DEFAULT_SETTINGS: CalibSettingsType = {
  n_starts: 3,
  tail_gamma: 2.0,
  ss_penalty: 5.0,
  normalize_per_file: true,
  R1_init: null,
  R2_init: null,
  h_nat_init: 10.0,
  h_rpm_init: 0.02,
  R1_bounds: null,
  R2_bounds: null,
};

export default function Calibration() {
  const {
    currentProfileId,
    testFileId,
    calibJobId,
    calibStatus,
    calibResult,
    setTestFile,
    setCurrentProfile,
    startCalib,
    updateProgress,
    finishCalib,
    errorCalib,
    resetCalib,
  } = useAppStore();

  const [step, setStep] = useState(0);
  const [profiles, setProfiles] = useState<MotorProfile[]>([]);
  const [selectedProfileId, setSelectedProfileId] = useState<string | null>(currentProfileId);
  const [geometry, setGeometry] = useState<MotorGeometry>(DEFAULT_GEOMETRY);
  const [material, setMaterial] = useState<MaterialProps>(DEFAULT_MATERIAL);
  const [profileName, setProfileName] = useState("New Motor");
  const [lossMode, setLossMode] = useState<"simple" | "map">("simple");
  const [settings, setSettings] = useState<CalibSettingsType>(DEFAULT_SETTINGS);
  const [columnMapping, setColumnMapping] = useState<Record<string, string | undefined>>({
    I_phase: "",
    T_amb: "",
    T_coil: "",
  });

  // File upload state
  const [uploadColumns, setUploadColumns] = useState<string[]>([]);
  const [uploadPreview, setUploadPreview] = useState<Record<string, unknown>[]>([]);
  const [lossMapFileId, setLossMapFileId] = useState<string | null>(null);

  // Simple iron loss params
  const [I_max, setIMax] = useState(10);
  const [RPM_max, setRPMMax] = useState(5000);
  const [alpha_iron, setAlphaIron] = useState(2.0);

  // Load profiles
  useEffect(() => {
    void (async () => {
      try {
        const list = await profilesApi.list();
        // list is MotorProfileSummary[], fetch full profiles
        const full = await Promise.all(list.map((p) => profilesApi.get(p.id)));
        setProfiles(full);
      } catch {
        // Silently fail — profiles will be empty
      }
    })();
  }, []);

  // SSE subscription for calibration progress
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
          errorCalib(event.message ?? "Unknown error");
        }
      },
      () => {
        errorCalib("Connection lost");
      },
    );

    return cleanup;
  }, [calibStatus, calibJobId, updateProgress, finishCalib, errorCalib]);

  const handleFileUploaded = useCallback(
    (fileId: string, response: FileUploadResponse) => {
      setTestFile(fileId);
      setUploadColumns(response.columns);
      setUploadPreview(response.preview);
      // Auto-map columns by name match
      const mapping: Record<string, string> = {};
      const targets = ["time", "rpm", "I_phase", "T_amb", "T_coil", "torque"];
      for (const col of response.columns) {
        const lower = col.toLowerCase().replace(/[\s_-]/g, "");
        for (const target of targets) {
          if (lower.includes(target.toLowerCase())) {
            mapping[target] = col;
          }
        }
      }
      setColumnMapping((prev) => ({
        ...prev,
        ...mapping,
        I_phase: mapping.I_phase || prev.I_phase,
        T_amb: mapping.T_amb || prev.T_amb,
        T_coil: mapping.T_coil || prev.T_coil,
      }));
    },
    [setTestFile],
  );

  async function handleStartCalibration() {
    // Ensure we have a profile
    let profileId = selectedProfileId;

    if (!profileId) {
      try {
        const newProfile = await profilesApi.create({
          name: profileName,
          geometry,
          material,
          iron_loss_mode: lossMode,
          simple_iron_loss:
            lossMode === "simple"
              ? { I_max, RPM_max, alpha_iron }
              : null,
        });
        profileId = newProfile.id;
        setSelectedProfileId(profileId);
        setCurrentProfile(profileId);
      } catch (err: unknown) {
        errorCalib(
          `Failed to create profile: ${err instanceof Error ? err.message : "Unknown error"}`,
        );
        return;
      }
    }

    if (!testFileId || !profileId) return;

    try {
      // Map columns first
      if (columnMapping.I_phase && columnMapping.T_amb && columnMapping.T_coil) {
        await filesApi.mapColumns(testFileId, {
          time: columnMapping.time || null,
          rpm: columnMapping.rpm || null,
          I_phase: columnMapping.I_phase,
          T_amb: columnMapping.T_amb,
          T_coil: columnMapping.T_coil,
          torque: columnMapping.torque || null,
        });
      }

      const jobId = await calibrationApi.start({
        profile_id: profileId,
        data_file_id: testFileId,
        loss_map_file_id: lossMode === "map" ? lossMapFileId : null,
        settings,
      });

      startCalib(jobId);
    } catch (err: unknown) {
      errorCalib(
        `Failed to start calibration: ${err instanceof Error ? err.message : "Unknown error"}`,
      );
    }
  }

  // Render based on calibration status
  if (calibStatus === "running") {
    return (
      <div className="p-6 max-w-3xl mx-auto">
        <CalibProgress />
      </div>
    );
  }

  if (calibStatus === "done" && calibResult) {
    return (
      <div className="p-6 max-w-4xl mx-auto">
        <CalibResults result={calibResult} />
        <div className="mt-6">
          <Button variant="outline" onClick={resetCalib}>
            New Calibration
          </Button>
        </div>
      </div>
    );
  }

  if (calibStatus === "error") {
    const errorMsg = useAppStore.getState().calibError;
    return (
      <div className="p-6 max-w-3xl mx-auto space-y-4">
        <div className="rounded-md border border-destructive/50 bg-destructive/10 px-4 py-3">
          <p className="text-sm text-destructive font-medium">
            Calibration Failed
          </p>
          <p className="text-xs text-destructive/80 mt-1">{errorMsg}</p>
        </div>
        <Button variant="outline" onClick={resetCalib}>
          Try Again
        </Button>
      </div>
    );
  }

  return (
    <div className="p-6 max-w-4xl mx-auto space-y-6">
      <h1 className="text-lg font-semibold">Calibration</h1>

      {/* Step indicator */}
      <div className="flex items-center gap-1">
        {STEPS.map((label, i) => (
          <button
            key={label}
            type="button"
            onClick={() => i < step && setStep(i)}
            className={`flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-medium transition-colors ${
              i === step
                ? "bg-primary text-primary-foreground"
                : i < step
                  ? "bg-muted text-foreground cursor-pointer hover:bg-muted/80"
                  : "text-muted-foreground"
            }`}
          >
            <span className="rounded-full size-5 flex items-center justify-center border border-current text-[10px]">
              {i + 1}
            </span>
            <span className="hidden sm:inline">{label}</span>
          </button>
        ))}
      </div>

      {/* Step content */}
      <div className="min-h-[400px]">
        {step === 0 && (
          <div className="space-y-4">
            <h2 className="text-sm font-semibold">Step 1: Upload Test Data</h2>
            <DataUpload
              fileType="test_data"
              fileId={testFileId}
              onFileUploaded={handleFileUploaded}
              columns={uploadColumns}
              preview={uploadPreview}
            />
          </div>
        )}

        {step === 1 && (
          <div className="space-y-4">
            <h2 className="text-sm font-semibold">
              Step 2: Motor Profile
            </h2>

            {/* Profile selector */}
            {profiles.length > 0 && (
              <div className="space-y-2">
                <select
                  className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
                  value={selectedProfileId ?? ""}
                  onChange={(e) => {
                    const id = e.target.value;
                    setSelectedProfileId(id || null);
                    if (id) {
                      const p = profiles.find((pr) => pr.id === id);
                      if (p) {
                        setGeometry(p.geometry);
                        setMaterial(p.material ?? DEFAULT_MATERIAL);
                        setProfileName(p.name);
                        setCurrentProfile(p.id);
                      }
                    }
                  }}
                >
                  <option value="">-- Create New Profile --</option>
                  {profiles.map((p) => (
                    <option key={p.id} value={p.id}>
                      {p.name}
                    </option>
                  ))}
                </select>
              </div>
            )}

            {!selectedProfileId && (
              <div className="space-y-2">
                <input
                  type="text"
                  className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
                  placeholder="Profile name"
                  value={profileName}
                  onChange={(e) => setProfileName(e.target.value)}
                />
                <MotorForm
                  geometry={geometry}
                  material={material}
                  onGeometryChange={setGeometry}
                  onMaterialChange={setMaterial}
                />
              </div>
            )}
          </div>
        )}

        {step === 2 && (
          <div className="space-y-4">
            <h2 className="text-sm font-semibold">Step 3: Loss Model</h2>

            <div className="flex gap-3">
              <button
                type="button"
                className={`rounded-md border px-4 py-2 text-sm ${
                  lossMode === "simple"
                    ? "border-primary bg-primary/10 text-primary"
                    : "border-border text-muted-foreground hover:bg-muted"
                }`}
                onClick={() => setLossMode("simple")}
              >
                Simple
              </button>
              <button
                type="button"
                className={`rounded-md border px-4 py-2 text-sm ${
                  lossMode === "map"
                    ? "border-primary bg-primary/10 text-primary"
                    : "border-border text-muted-foreground hover:bg-muted"
                }`}
                onClick={() => setLossMode("map")}
              >
                FEA Loss Map
              </button>
            </div>

            {lossMode === "simple" && (
              <div className="space-y-3">
                <div className="flex items-center gap-2">
                  <label className="w-24 text-xs text-muted-foreground">
                    I_max [A]
                  </label>
                  <input
                    type="number"
                    step="any"
                    className="w-28 rounded-md border border-input bg-background px-2 py-1 text-sm font-mono tabular-nums"
                    value={I_max}
                    onChange={(e) => setIMax(parseFloat(e.target.value))}
                  />
                </div>
                <div className="flex items-center gap-2">
                  <label className="w-24 text-xs text-muted-foreground">
                    RPM_max
                  </label>
                  <input
                    type="number"
                    step="any"
                    className="w-28 rounded-md border border-input bg-background px-2 py-1 text-sm font-mono tabular-nums"
                    value={RPM_max}
                    onChange={(e) => setRPMMax(parseFloat(e.target.value))}
                  />
                </div>
                <div className="flex items-center gap-2">
                  <label className="w-24 text-xs text-muted-foreground">
                    alpha_iron
                  </label>
                  <input
                    type="number"
                    step="any"
                    className="w-28 rounded-md border border-input bg-background px-2 py-1 text-sm font-mono tabular-nums"
                    value={alpha_iron}
                    onChange={(e) => setAlphaIron(parseFloat(e.target.value))}
                  />
                </div>
              </div>
            )}

            {lossMode === "map" && (
              <DataUpload
                fileType="loss_map"
                fileId={lossMapFileId}
                onFileUploaded={(id) => setLossMapFileId(id)}
                columns={[]}
                preview={[]}
              />
            )}
          </div>
        )}

        {step === 3 && (
          <div className="space-y-4">
            <h2 className="text-sm font-semibold">
              Step 4: Calibration Settings
            </h2>
            <CalibSettingsForm
              settings={settings}
              onSettingsChange={setSettings}
              columns={uploadColumns}
              columnMapping={columnMapping}
              onColumnMappingChange={setColumnMapping}
              fileId={testFileId}
            />

            <Button
              onClick={() => void handleStartCalibration()}
              disabled={!testFileId}
            >
              Start Calibration
            </Button>
          </div>
        )}
      </div>

      {/* Navigation */}
      <div className="flex justify-between pt-4 border-t border-border">
        <Button
          variant="outline"
          onClick={() => setStep((s) => Math.max(0, s - 1))}
          disabled={step === 0}
        >
          Previous
        </Button>
        <Button
          onClick={() => setStep((s) => Math.min(STEPS.length - 1, s + 1))}
          disabled={step === STEPS.length - 1}
        >
          Next
        </Button>
      </div>
    </div>
  );
}
