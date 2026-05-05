import { useState, useEffect, useCallback } from "react";
import { useAppStore } from "@/stores/appStore";
import { profilesApi, calibrationApi, filesApi } from "@/lib/api";
import type { MotorProfile, MotorGeometry, MaterialProps } from "@/types/motor";
import type { CalibSettings as CalibSettingsType, CalibProgressEvent } from "@/types/calibration";
import type { FileUploadResponse, FileConditionSummary, ColumnMappingRequest } from "@/types/data";
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
    testFileIds,
    calibJobId,
    calibStatus,
    calibResult,
    setTestFile,
    setTestFiles,
    removeTestFile,
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

  // Multi-file state
  const [uploadedFiles, setUploadedFiles] = useState<FileUploadResponse[]>([]);
  const [fileConditions, setFileConditions] = useState<Map<string, FileConditionSummary>>(
    new Map(),
  );

  // Simple iron loss params
  const [I_max, setIMax] = useState(10);
  const [RPM_max, setRPMMax] = useState(5000);
  const [alpha_iron, setAlphaIron] = useState(2.0);

  // Load profiles
  useEffect(() => {
    void (async () => {
      try {
        const list = await profilesApi.list();
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
      // Set single-file reference for backwards compatibility
      setTestFile(fileId);

      // Add to multi-file list
      setUploadedFiles((prev) => {
        if (prev.some((f) => f.file_id === fileId)) return prev;
        return [...prev, response];
      });

      setUploadColumns(response.columns);
      setUploadPreview(response.preview);

      // Update file IDs array in store
      setTestFiles(
        [...uploadedFiles.map((f) => f.file_id), fileId].filter(
          (id, idx, arr) => arr.indexOf(id) === idx,
        ),
      );

      // Auto-map columns — supports both simple names and power analyzer
      // formats like "I SigA[A]", "TS.Spd[/min]", "Cham.ComTemp[°C]"
      const mapping: Record<string, string> = {};
      const cols = response.columns;
      const lc = cols.map((c) => c.toLowerCase());

      // time: look for "time" + "sec" or plain "time"
      {
        const idx = lc.findIndex((c) => c.includes("time") && c.includes("sec"));
        if (idx >= 0) mapping.time = cols[idx];
        else {
          const i2 = lc.findIndex((c) => c === "time");
          if (i2 >= 0) mapping.time = cols[i2];
        }
      }

      // rpm: look for "spd" + "/min" or "rpm"
      {
        const idx = lc.findIndex((c) => c.includes("spd") && c.includes("/min"));
        if (idx >= 0) mapping.rpm = cols[idx];
        else {
          const i2 = lc.findIndex((c) => c.includes("rpm"));
          if (i2 >= 0) mapping.rpm = cols[i2];
        }
      }

      // I_phase: prefer "i sig" + "[a]" (total RMS), then "i1" + "[a]", then "i_phase"
      {
        const idx = lc.findIndex((c) => c.includes("i sig") && c.includes("[a]"));
        if (idx >= 0) mapping.I_phase = cols[idx];
        else {
          const i2 = lc.findIndex((c) => /^i\d+\[a\]/.test(c));
          if (i2 >= 0) mapping.I_phase = cols[i2];
          else {
            const i3 = lc.findIndex((c) => c.includes("i_phase") || c.includes("iphase"));
            if (i3 >= 0) mapping.I_phase = cols[i3];
          }
        }
      }

      // T_amb: prefer "cham" or "amb" or "comtemp", then plain "t_amb"
      {
        const idx = lc.findIndex(
          (c) => c.includes("cham") || c.includes("amb") || c.includes("comtemp"),
        );
        if (idx >= 0) mapping.T_amb = cols[idx];
        else {
          const i2 = lc.findIndex((c) => c.includes("t_amb") || c.includes("tamb"));
          if (i2 >= 0) mapping.T_amb = cols[i2];
        }
      }

      // T_coil: prefer "temp1[" (first thermocouple = likely coil), then "load.temp",
      // then any "temp" + digit, then plain "t_coil"
      {
        const idx = lc.findIndex((c) => /^temp1\[/.test(c));
        if (idx >= 0) mapping.T_coil = cols[idx];
        else {
          const i2 = lc.findIndex((c) => c.includes("load") && c.includes("temp"));
          if (i2 >= 0) mapping.T_coil = cols[i2];
          else {
            const i3 = lc.findIndex((c) => /^temp\d+\[/.test(c));
            if (i3 >= 0) mapping.T_coil = cols[i3];
            else {
              const i4 = lc.findIndex((c) => c.includes("t_coil") || c.includes("tcoil"));
              if (i4 >= 0) mapping.T_coil = cols[i4];
            }
          }
        }
      }

      // torque: prefer "trq" + "[n", then plain "torque"
      {
        const idx = lc.findIndex((c) => c.includes("trq") && c.includes("[n"));
        if (idx >= 0) mapping.torque = cols[idx];
        else {
          const i2 = lc.findIndex((c) => c.includes("torque"));
          if (i2 >= 0) mapping.torque = cols[i2];
        }
      }
      setColumnMapping((prev) => ({
        ...prev,
        ...mapping,
        I_phase: mapping.I_phase || prev.I_phase,
        T_amb: mapping.T_amb || prev.T_amb,
        T_coil: mapping.T_coil || prev.T_coil,
      }));

      // Fetch conditions for the uploaded file
      void (async () => {
        try {
          const mappingRequest: ColumnMappingRequest = {
            time: mapping.time || null,
            rpm: mapping.rpm || null,
            I_phase: mapping.I_phase || "",
            T_amb: mapping.T_amb || "",
            T_coil: mapping.T_coil || "",
            torque: mapping.torque || null,
          };
          // Only fetch conditions if we have the required column mappings
          if (mappingRequest.I_phase && mappingRequest.T_amb && mappingRequest.T_coil) {
            const cond = await filesApi.getConditions(fileId, mappingRequest);
            setFileConditions((prev) => new Map(prev).set(fileId, cond));
          }
        } catch {
          // Conditions are optional — silently continue
        }
      })();
    },
    [setTestFile, setTestFiles, uploadedFiles],
  );

  const handleRemoveFile = useCallback(
    (fileId: string) => {
      removeTestFile(fileId);
      setUploadedFiles((prev) => prev.filter((f) => f.file_id !== fileId));
      setFileConditions((prev) => {
        const next = new Map(prev);
        next.delete(fileId);
        return next;
      });
    },
    [removeTestFile],
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

    const fileIds = testFileIds.length > 0 ? testFileIds : testFileId ? [testFileId] : [];
    if (fileIds.length === 0 || !profileId) return;

    try {
      // Map columns for each file
      if (columnMapping.I_phase && columnMapping.T_amb && columnMapping.T_coil) {
        const mappingRequest: ColumnMappingRequest = {
          time: columnMapping.time || null,
          rpm: columnMapping.rpm || null,
          I_phase: columnMapping.I_phase,
          T_amb: columnMapping.T_amb,
          T_coil: columnMapping.T_coil,
          torque: columnMapping.torque || null,
        };
        await Promise.all(fileIds.map((fid) => filesApi.mapColumns(fid, mappingRequest)));
      }

      const jobId = await calibrationApi.start({
        profile_id: profileId,
        data_file_ids: fileIds,
        loss_map_file_id: lossMode === "map" ? lossMapFileId : null,
        column_mapping:
          columnMapping.I_phase && columnMapping.T_amb && columnMapping.T_coil
            ? {
                time: columnMapping.time || null,
                rpm: columnMapping.rpm || null,
                I_phase: columnMapping.I_phase,
                T_amb: columnMapping.T_amb,
                T_coil: columnMapping.T_coil,
                torque: columnMapping.torque || null,
              }
            : null,
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

  // Determine which file ID to pass to single-file components
  const activeFileId = testFileIds.length > 0 ? testFileIds[0] : testFileId;
  const hasFiles = testFileIds.length > 0 || testFileId !== null;

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
              fileId={activeFileId}
              onFileUploaded={handleFileUploaded}
              columns={uploadColumns}
              preview={uploadPreview}
              multiple
              uploadedFiles={uploadedFiles}
              fileConditions={fileConditions}
              onRemoveFile={handleRemoveFile}
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
              fileId={activeFileId}
            />

            {/* Per-file summary for multi-file */}
            {uploadedFiles.length > 1 && (
              <div className="space-y-2">
                <p className="text-xs font-semibold text-muted-foreground">
                  Files to calibrate ({uploadedFiles.length})
                </p>
                <div className="flex flex-wrap gap-1.5">
                  {uploadedFiles.map((f) => (
                    <span
                      key={f.file_id}
                      className="rounded bg-muted px-2 py-0.5 text-xs font-mono"
                    >
                      {f.filename}
                    </span>
                  ))}
                </div>
              </div>
            )}

            <Button
              onClick={() => void handleStartCalibration()}
              disabled={!hasFiles}
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
