// TypeScript types matching backend /api/compressor/ endpoints

// ---------------------------------------------------------------------------
// Upload
// ---------------------------------------------------------------------------
export interface CompressorSheetInfo {
  sheet_name: string;
  variant_name: string | null;
  n_points: number;
  columns_found: string[];
  columns_missing: string[];
  errors: string[];
}

export interface CompressorUploadResponse {
  filename: string;
  sheets: CompressorSheetInfo[];
  total_points: number;
  valid_sheets: number;
  invalid_sheets: number;
}

// ---------------------------------------------------------------------------
// Datasets
// ---------------------------------------------------------------------------
export interface CompressorDataset {
  filename: string;
  sheets: CompressorSheetInfo[];
  total_points: number;
}

export interface CompressorDatasetsResponse {
  datasets: CompressorDataset[];
}

// ---------------------------------------------------------------------------
// Prediction
// ---------------------------------------------------------------------------
export interface CompressorPredictRequest {
  RPM: number;
  Ps: number;
  Ts: number;
  Pd: number;
  params?: CompressorThermalParams | null;
  motor_params?: CompressorMotorParams | null;
}

export interface CompressorThermalParams {
  UA_0: number;
  UA_1: number;
  eta_vol: number;
  eta_s: number;
  R_coil_core: number;
  h_ref: number;
}

export interface CompressorMotorParams {
  R: number;
  V_displ: number;
  I_peak: number;
  IronLoss: number;
}

export interface CompressorPrediction {
  Tm: number;
  Td: number;
  Torque: number;
  Q_recirc: number;
  MotorLoss: number;
  hm: number;
  hd: number;
  mdot: number;
}

export interface CompressorPredictResponse {
  prediction: CompressorPrediction;
  converged: boolean;
  iterations: number;
  residual: number;
}

// ---------------------------------------------------------------------------
// Calibration
// ---------------------------------------------------------------------------
export interface CompressorCalibrateConfig {
  n_starts?: number | null;
  ftol?: number | null;
  max_iter?: number | null;
}

export interface CompressorCalibrateRequest {
  dataset_id: string;
  sheet_names?: string[] | null;
  config?: CompressorCalibrateConfig | null;
}

export interface CompressorCalibResult {
  params: CompressorThermalParams & {
    motor_params?: CompressorMotorParams | null;
  };
  rmse_Tm: number;
  rmse_Torque: number;
  converged: boolean;
  iterations: number;
  time_s: number;
  loss_history: number[];
  Tm_predicted: number[];
  Tm_measured: number[];
  Torque_predicted: number[];
  Torque_measured: number[];
  RPM_array: number[];
}

// SSE progress event types for compressor calibration
export interface CompressorCalibProgressEvent {
  type: "progress" | "done" | "error";
  iter?: number | null;
  rmse_Tm?: number | null;
  rmse_Torque?: number | null;
  elapsed?: number | null;
  message?: string | null;
  result?: CompressorCalibResult | null;
}

// ---------------------------------------------------------------------------
// Energy Balance Prediction
// ---------------------------------------------------------------------------
export interface LookupEntry {
  x: number; // I or Torque
  y: number; // Torque or Loss
}

export interface LookupTableInput {
  rpm: number;
  entries: LookupEntry[];
}

export interface CompressorEnergyRequest {
  // Refrigerant conditions
  Ps: number; // Suction pressure [barG]
  Ts: number; // Suction temperature [degC]
  P_mid: number; // Mid-point pressure [barG]
  T_mid: number; // Mid-point temperature [degC]
  Pd: number; // Discharge pressure [barG]
  mdot: number; // Mass flow rate [kg/h]
  // Motor electrical
  V: number; // Line-to-line voltage [V]
  I: number; // Phase current [A]
  RPM: number; // Motor speed [rpm]
  // Lookup tables
  torque_table: LookupTableInput[];
  loss_table: LookupTableInput[];
  // Thermal
  R_coil_case: number; // [K/W]
  R_coil_core: number; // [K/W]
  R_coil_refrigerant: number; // [K/W]
  T_ambient: number; // [degC]
}

export interface CompressorEnergyResponse {
  Torque: number;
  T_coil: number;
  Pin: number;
  Pmech: number;
  MotorLoss: number;
  Q_refrig: number;
  Q_ambient: number;
  hs: number;
  h_mid: number;
  hd: number;
  Td_est: number;
  mdot_recirc: number;
  recirc_ratio: number;
  balance_error_pct: number;
  converged: boolean;
}

// ---------------------------------------------------------------------------
// Calibration (energy-balance model)
// ---------------------------------------------------------------------------
export interface CalibDataPoint {
  Ps: number;
  Ts: number;
  P_mid: number;
  T_mid: number;
  Pd: number;
  mdot: number;
  V: number;
  I: number;
  RPM: number;
  T_ambient?: number;
  T_coil_measured: number;
  Td_measured?: number | null;
}

export interface CalibConfig {
  n_starts?: number | null;
  tol?: number | null;
  max_iter?: number | null;
}

export interface EnergyCalibRequest {
  data_points: CalibDataPoint[];
  torque_table: LookupTableInput[];
  loss_table: LookupTableInput[];
  R_init?: Record<string, number> | null;
  config?: CalibConfig | null;
}

export interface EnergyCalibResult {
  R_coil_case: number;
  R_coil_core: number;
  R_coil_refrigerant: number;
  rmse_T_coil: number;
  mae_T_coil: number;
  max_error_T_coil: number;
  rmse_Td: number | null;
  n_points: number;
  converged: boolean;
  iterations: number;
  T_coil_predicted: number[];
  T_coil_measured: number[];
  Td_predicted: number[];
}
