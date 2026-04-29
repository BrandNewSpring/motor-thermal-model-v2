// TypeScript types matching backend schemas/motor.py

export interface MotorGeometry {
  D_motor_mm: number;
  L_motor_mm: number;
  m_motor_g: number;
  t_housing_mm: number;
  L_housing_mm: number | null;
  m_housing_g: number;
  t_mold_mm: number;
  f_copper: number;
}

export interface MaterialProps {
  c_p_Cu: number;
  c_p_FeSi: number;
  c_p_Al: number;
  k_mold: number;
  beta_iron: number;
}

export interface CoilParams {
  R0: number;
  T0: number;
  alpha: number;
  n_phases: number;
}

export type IronLossMode = "simple" | "map";

export interface SimpleIronLoss {
  I_max: number;
  RPM_max: number;
  alpha_iron: number;
}

export interface GeometryPreview {
  C_coil: number;
  C_core: number;
  C_housing: number;
  A_interface_m2: number;
  A_housing_m2: number;
  R2_mold_init: number;
  R3_nat_init: number;
  tau_coil_s: number;
}

export interface MotorProfileCreate {
  name: string;
  geometry: MotorGeometry;
  material?: MaterialProps;
  coil?: CoilParams;
  iron_loss_mode: IronLossMode;
  simple_iron_loss?: SimpleIronLoss | null;
}

export type MotorProfileUpdate = Partial<{
  name: string;
  geometry: MotorGeometry;
  material: MaterialProps;
  coil: CoilParams;
  iron_loss_mode: IronLossMode;
  simple_iron_loss: SimpleIronLoss | null;
}>;

export interface MotorProfileSummary {
  id: string;
  name: string;
  created_at: string;
  updated_at: string;
  iron_loss_mode: IronLossMode;
}

export interface MotorProfile extends MotorProfileCreate {
  id: string;
  created_at: string;
  updated_at: string;
  geometry_preview: GeometryPreview | null;
}
