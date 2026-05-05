import { useState, useCallback } from "react";
import type {
  CompressorUploadResponse,
  CompressorEnergyResponse,
  EnergyCalibResult,
  LookupTableInput,
} from "@/types/compressor";
import type { PredictionInputs } from "@/components/compressor/CompressorResults";
import CompressorUpload from "@/components/compressor/CompressorUpload";
import CompressorPredict from "@/components/compressor/CompressorPredict";
import CompressorCalibrate from "@/components/compressor/CompressorCalibrate";
import CompressorResults from "@/components/compressor/CompressorResults";

const TABS = ["Upload", "Predict", "Calibrate", "Results"] as const;
type Tab = (typeof TABS)[number];

const DEFAULT_TORQUE_TABLE: LookupTableInput[] = [
  { rpm: 2000, entries: [{ x: 3, y: 0.5 }, { x: 5, y: 0.9 }, { x: 7, y: 1.3 }] },
  { rpm: 3000, entries: [{ x: 3, y: 0.4 }, { x: 5, y: 0.8 }, { x: 7, y: 1.2 }] },
  { rpm: 4000, entries: [{ x: 3, y: 0.3 }, { x: 5, y: 0.7 }, { x: 7, y: 1.1 }] },
];

const DEFAULT_LOSS_TABLE: LookupTableInput[] = [
  { rpm: 2000, entries: [{ x: 0.5, y: 30 }, { x: 0.9, y: 50 }, { x: 1.3, y: 80 }] },
  { rpm: 3000, entries: [{ x: 0.4, y: 35 }, { x: 0.8, y: 55 }, { x: 1.2, y: 85 }] },
  { rpm: 4000, entries: [{ x: 0.3, y: 40 }, { x: 0.7, y: 60 }, { x: 1.1, y: 90 }] },
];

export default function Compressor() {
  const [activeTab, setActiveTab] = useState<Tab>("Upload");

  // Upload state
  const [uploadResponse, setUploadResponse] = useState<CompressorUploadResponse | null>(null);

  // Lookup tables (shared between Predict and Calibrate)
  const [torqueTable, setTorqueTable] = useState<LookupTableInput[]>(DEFAULT_TORQUE_TABLE);
  const [lossTable, setLossTable] = useState<LookupTableInput[]>(DEFAULT_LOSS_TABLE);

  // Prediction state
  const [prediction, setPrediction] = useState<CompressorEnergyResponse | null>(null);
  const [predictionInputs, setPredictionInputs] = useState<PredictionInputs | null>(null);

  // Calibration state
  const [calibResult, setCalibResult] = useState<EnergyCalibResult | null>(null);

  const handleUploaded = useCallback((response: CompressorUploadResponse) => {
    setUploadResponse(response);
    setActiveTab("Predict");
  }, []);

  const handlePredictionResult = useCallback((result: CompressorEnergyResponse, inputs?: PredictionInputs) => {
    setPrediction(result);
    if (inputs) setPredictionInputs(inputs);
    setActiveTab("Results");
  }, []);

  const handleCalibResult = useCallback((result: EnergyCalibResult) => {
    setCalibResult(result);
  }, []);

  return (
    <div className="p-6 max-w-4xl mx-auto space-y-6">
      <h1 className="text-lg font-semibold">Compressor Thermal Model</h1>

      {/* Tab bar */}
      <div className="flex items-center gap-1">
        {TABS.map((tab) => (
          <button
            key={tab}
            type="button"
            onClick={() => setActiveTab(tab)}
            className={`px-4 py-1.5 rounded-md text-sm font-medium transition-colors ${
              activeTab === tab
                ? "bg-primary text-primary-foreground"
                : "text-muted-foreground hover:bg-muted hover:text-foreground"
            }`}
          >
            {tab}
          </button>
        ))}
      </div>

      {/* Tab content */}
      <div className="min-h-[400px]">
        {activeTab === "Upload" && (
          <CompressorUpload
            onUploaded={handleUploaded}
            filename={uploadResponse?.filename ?? null}
          />
        )}

        {activeTab === "Predict" && (
          <CompressorPredict
            onResult={handlePredictionResult}
            torqueTable={torqueTable}
            lossTable={lossTable}
            onTorqueTableChange={setTorqueTable}
            onLossTableChange={setLossTable}
          />
        )}

        {activeTab === "Calibrate" && (
          <CompressorCalibrate
            torqueTable={torqueTable}
            lossTable={lossTable}
            onResult={handleCalibResult}
          />
        )}

        {activeTab === "Results" && (
          <CompressorResults
            prediction={prediction}
            calibResult={calibResult}
            predictionInputs={predictionInputs}
          />
        )}
      </div>
    </div>
  );
}
