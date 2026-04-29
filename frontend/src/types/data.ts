// TypeScript types matching backend schemas/data.py

export interface FileUploadResponse {
  file_id: string;
  filename: string;
  rows: number;
  columns: string[];
  preview: Record<string, unknown>[];
}

export interface FileColumnsResponse {
  columns: string[];
  sample: Record<string, unknown>[];
}

export interface ColumnMappingRequest {
  time?: string | null;
  rpm?: string | null;
  I_phase: string;
  T_amb: string;
  T_coil: string;
  torque?: string | null;
}

export interface ColumnMappingResponse {
  mapped_rows: number;
  summary: Record<string, unknown>;
}

export interface SteadyStateRequest {
  profile_id: string;
  I_phase: number;
  T_amb: number;
  rpm: number;
  R1?: number | null;
  R2?: number | null;
  h_nat?: number | null;
  h_rpm?: number | null;
}

export interface SteadyStateResult {
  T_coil_ss: number;
  T_core_ss: number;
  T_housing_ss: number;
  Q_copper: number;
  Q_iron: number;
  R3_at_rpm: number;
}

export interface GridPredictionRequest {
  profile_id: string;
  I_range: [number, number];
  RPM_range: [number, number];
  T_amb: number;
  n_points: number;
  R1?: number | null;
  R2?: number | null;
  h_nat?: number | null;
  h_rpm?: number | null;
}

export interface GridPredictionResult {
  grid_I: number[][];
  grid_RPM: number[][];
  grid_T_coil: number[][];
  grid_T_core: number[][];
  grid_T_housing: number[][];
}

export interface ExportRequest {
  profile_id: string;
  job_id?: string | null;
  include_grid: boolean;
}
