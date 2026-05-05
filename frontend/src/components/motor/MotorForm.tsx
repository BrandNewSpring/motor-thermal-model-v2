import { useState, useEffect, useCallback } from "react";
import type { MotorGeometry, MaterialProps, GeometryPreview } from "@/types/motor";
import { profilesApi } from "@/lib/api";

interface MotorFormProps {
  geometry: MotorGeometry;
  material: MaterialProps;
  onGeometryChange: (geo: MotorGeometry) => void;
  onMaterialChange: (mat: MaterialProps) => void;
}

const GEO_FIELDS: { key: keyof MotorGeometry; label: string; unit: string }[] = [
  { key: "D_motor_mm", label: "Stator Diameter", unit: "mm" },
  { key: "L_motor_mm", label: "Stator Length", unit: "mm" },
  { key: "m_motor_g", label: "Motor Mass", unit: "g" },
  { key: "t_housing_mm", label: "Housing Thickness", unit: "mm" },
  { key: "L_housing_mm", label: "Housing Length", unit: "mm" },
  { key: "m_housing_g", label: "Housing Mass", unit: "g" },
  { key: "t_mold_mm", label: "Mold Thickness", unit: "mm" },
  { key: "f_copper", label: "Copper Fill", unit: "" },
];

const MAT_FIELDS: { key: keyof MaterialProps; label: string; unit: string }[] = [
  { key: "c_p_Cu", label: "Copper c_p", unit: "J/(kg*K)" },
  { key: "c_p_FeSi", label: "Steel c_p", unit: "J/(kg*K)" },
  { key: "c_p_Al", label: "Aluminum c_p", unit: "J/(kg*K)" },
  { key: "k_mold", label: "Mold Conductivity", unit: "W/(m*K)" },
  { key: "beta_iron", label: "Iron Temp Coeff", unit: "1/K" },
];

export default function MotorForm({
  geometry,
  material,
  onGeometryChange,
  onMaterialChange,
}: MotorFormProps) {
  const [preview, setPreview] = useState<GeometryPreview | null>(null);
  const [loading, setLoading] = useState(false);

  const computePreview = useCallback(async () => {
    setLoading(true);
    try {
      const result = await profilesApi.computeGeometry(geometry, material);
      setPreview(result);
    } catch {
      setPreview(null);
    } finally {
      setLoading(false);
    }
  }, [geometry, material]);

  useEffect(() => {
    const timer = setTimeout(computePreview, 400);
    return () => clearTimeout(timer);
  }, [computePreview]);

  function handleGeoChange(key: keyof MotorGeometry, value: string) {
    if (key === "L_housing_mm") {
      // L_housing_mm is the only nullable geometry field
      const num = value === "" ? null : parseFloat(value);
      onGeometryChange({ ...geometry, [key]: num as number | null });
      return;
    }
    const num = parseFloat(value);
    // Guard: keep previous valid value if input is empty or NaN
    if (value === "" || Number.isNaN(num)) {
      return;
    }
    onGeometryChange({ ...geometry, [key]: num });
  }

  function handleMatChange(key: keyof MaterialProps, value: string) {
    const num = parseFloat(value);
    // Guard: keep previous valid value if input is empty or NaN
    if (value === "" || Number.isNaN(num)) {
      return;
    }
    onMaterialChange({ ...material, [key]: num });
  }

  return (
    <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
      {/* Geometry Inputs */}
      <div className="space-y-3">
        <h3 className="text-sm font-semibold text-foreground">Geometry</h3>
        {GEO_FIELDS.map(({ key, label, unit }) => (
          <div key={key} className="flex items-center gap-2">
            <label className="w-36 text-xs text-muted-foreground shrink-0">
              {label}
            </label>
            <input
              type="number"
              step="any"
              className="flex-1 rounded-md border border-input bg-background px-2 py-1 text-sm font-mono tabular-nums"
              value={geometry[key] ?? ""}
              onChange={(e) => handleGeoChange(key, e.target.value)}
            />
            {unit && (
              <span className="text-xs text-muted-foreground w-16">{unit}</span>
            )}
          </div>
        ))}
      </div>

      {/* Material Inputs */}
      <div className="space-y-3">
        <h3 className="text-sm font-semibold text-foreground">Material</h3>
        {MAT_FIELDS.map(({ key, label, unit }) => (
          <div key={key} className="flex items-center gap-2">
            <label className="w-36 text-xs text-muted-foreground shrink-0">
              {label}
            </label>
            <input
              type="number"
              step="any"
              className="flex-1 rounded-md border border-input bg-background px-2 py-1 text-sm font-mono tabular-nums"
              value={material[key]}
              onChange={(e) => handleMatChange(key, e.target.value)}
            />
            {unit && (
              <span className="text-xs text-muted-foreground w-16">{unit}</span>
            )}
          </div>
        ))}

        {/* Geometry Preview */}
        {preview && (
          <div className="mt-4 rounded-md border border-border bg-muted/40 p-3 space-y-1.5">
            <h4 className="text-xs font-semibold text-foreground">
              Computed Preview
            </h4>
            <div className="grid grid-cols-2 gap-x-4 gap-y-1 text-xs">
              <PreviewItem label="C_coil" value={preview.C_coil} unit="J/degC" />
              <PreviewItem label="C_core" value={preview.C_core} unit="J/degC" />
              <PreviewItem label="C_housing" value={preview.C_housing} unit="J/degC" />
              <PreviewItem label="R2_mold" value={preview.R2_mold_init} unit="degC/W" />
              <PreviewItem label="R3_nat" value={preview.R3_nat_init} unit="degC/W" />
              <PreviewItem label="tau_coil" value={preview.tau_coil_s} unit="s" />
            </div>
          </div>
        )}
        {loading && (
          <p className="text-xs text-muted-foreground">Computing...</p>
        )}
      </div>
    </div>
  );
}

function PreviewItem({
  label,
  value,
  unit,
}: {
  label: string;
  value: number;
  unit: string;
}) {
  return (
    <div className="flex items-baseline gap-1">
      <span className="text-muted-foreground">{label}:</span>
      <span className="font-mono tabular-nums">{value.toFixed(3)}</span>
      <span className="text-muted-foreground">{unit}</span>
    </div>
  );
}
