// TypeScript types matching backend schemas/calibration.py

export interface CalibSettings {
  n_starts: number;
  tail_gamma: number;
  ss_penalty: number;
  normalize_per_file: boolean;
  R1_init: number | null;
  R2_init: number | null;
  h_nat_init: number;
  h_rpm_init: number;
  R1_bounds: [number, number] | null;
  R2_bounds: [number, number] | null;
}

export interface CalibRequest {
  profile_id: string;
  data_file_id: string;
  loss_map_file_id?: string | null;
  settings: CalibSettings;
}

export interface ColumnMapping {
  time?: string | null;
  rpm?: string | null;
  I_phase: string;
  T_amb: string;
  T_coil: string;
  torque?: string | null;
}

export interface ThermalParams {
  R1: number;
  R2: number;
  h_nat: number;
  h_rpm: number;
  C_coil: number;
  C_core: number;
  C_housing: number;
  R2_mold: number | null;
}

export interface CalibResult {
  params: ThermalParams;
  rmse: number;
  r_squared: number;
  T_coil_sim: number[];
  T_core_sim: number[];
  T_housing_sim: number[];
  residuals: number[];
  time_s: number;
  converged: boolean;
  loss_history: number[];
}

// SSE progress event types
export interface CalibProgressEvent {
  type: "progress" | "phase" | "done" | "error";
  start?: number | null;
  n_starts?: number | null;
  iter?: number | null;
  rmse?: number | null;
  elapsed?: number | null;
  message?: string | null;
  result?: CalibResult | null;
}
