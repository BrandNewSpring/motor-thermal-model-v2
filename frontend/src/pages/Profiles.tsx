import { useState, useEffect, useCallback } from "react";
import { profilesApi } from "@/lib/api";
import type { MotorProfile, MotorGeometry } from "@/types/motor";
import { useAppStore } from "@/stores/appStore";
import { Button } from "@/components/ui/button";
import { Plus, Copy, Trash2, Edit3 } from "lucide-react";

export default function Profiles() {
  const { setCurrentProfile } = useAppStore();
  const [profiles, setProfiles] = useState<MotorProfile[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Modal state
  const [editProfile, setEditProfile] = useState<MotorProfile | null>(null);
  const [showCreate, setShowCreate] = useState(false);

  // Delete confirmation
  const [deleteTarget, setDeleteTarget] = useState<string | null>(null);

  const loadProfiles = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const list = await profilesApi.list();
      const full = await Promise.all(list.map((p) => profilesApi.get(p.id)));
      setProfiles(full);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Failed to load profiles");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadProfiles();
  }, [loadProfiles]);

  async function handleDelete(id: string) {
    try {
      await profilesApi.delete(id);
      setProfiles((prev) => prev.filter((p) => p.id !== id));
      setDeleteTarget(null);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Delete failed");
    }
  }

  async function handleCopy(id: string) {
    try {
      const copied = await profilesApi.copy(id);
      setProfiles((prev) => [...prev, copied]);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Copy failed");
    }
  }

  if (loading) {
    return (
      <div className="p-6 text-sm text-muted-foreground">Loading profiles...</div>
    );
  }

  return (
    <div className="p-6 max-w-5xl mx-auto space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-lg font-semibold">Motor Profiles</h1>
        <Button
          onClick={() => {
            setEditProfile(null);
            setShowCreate(true);
          }}
        >
          <Plus className="size-4 mr-1" />
          New Profile
        </Button>
      </div>

      {error && (
        <div className="rounded-md border border-destructive/50 bg-destructive/10 px-3 py-2">
          <p className="text-xs text-destructive">{error}</p>
        </div>
      )}

      {/* Profile grid */}
      {profiles.length === 0 ? (
        <p className="text-sm text-muted-foreground">
          No profiles yet. Create one to get started.
        </p>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {profiles.map((profile) => (
            <div
              key={profile.id}
              className="rounded-lg border border-border bg-card p-4 space-y-3 hover:border-primary/30 transition-colors"
            >
              <div className="flex items-start justify-between">
                <div>
                  <h3 className="text-sm font-semibold text-foreground">
                    {profile.name}
                  </h3>
                  <p className="text-xs text-muted-foreground mt-0.5">
                    {profile.iron_loss_mode} mode
                  </p>
                </div>
                <div className="flex gap-1">
                  <button
                    type="button"
                    onClick={() => {
                      setEditProfile(profile);
                      setShowCreate(true);
                    }}
                    className="rounded p-1 text-muted-foreground hover:bg-muted hover:text-foreground"
                    aria-label="Edit profile"
                  >
                    <Edit3 className="size-3.5" />
                  </button>
                  <button
                    type="button"
                    onClick={() => void handleCopy(profile.id)}
                    className="rounded p-1 text-muted-foreground hover:bg-muted hover:text-foreground"
                    aria-label="Copy profile"
                  >
                    <Copy className="size-3.5" />
                  </button>
                  <button
                    type="button"
                    onClick={() => setDeleteTarget(profile.id)}
                    className="rounded p-1 text-muted-foreground hover:bg-destructive/10 hover:text-destructive"
                    aria-label="Delete profile"
                  >
                    <Trash2 className="size-3.5" />
                  </button>
                </div>
              </div>

              {/* Geometry summary */}
              <div className="text-xs text-muted-foreground space-y-0.5">
                <p>
                  D={profile.geometry.D_motor_mm}mm, L=
                  {profile.geometry.L_motor_mm}mm
                </p>
                <p>
                  m_motor={profile.geometry.m_motor_g}g, f_copper=
                  {profile.geometry.f_copper}
                </p>
              </div>

              {/* Geometry preview */}
              {profile.geometry_preview && (
                <div className="rounded border border-border bg-muted/30 p-2 text-xs space-y-0.5">
                  <p>
                    C_coil:{" "}
                    <span className="font-mono tabular-nums">
                      {profile.geometry_preview.C_coil.toFixed(2)}
                    </span>{" "}
                    J/degC
                  </p>
                  <p>
                    C_core:{" "}
                    <span className="font-mono tabular-nums">
                      {profile.geometry_preview.C_core.toFixed(2)}
                    </span>{" "}
                    J/degC
                  </p>
                  <p>
                    tau:{" "}
                    <span className="font-mono tabular-nums">
                      {profile.geometry_preview.tau_coil_s.toFixed(1)}
                    </span>{" "}
                    s
                  </p>
                </div>
              )}

              <div className="flex justify-end">
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => setCurrentProfile(profile.id)}
                >
                  Use for Calibration
                </Button>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Delete confirmation dialog */}
      {deleteTarget && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
          <div className="rounded-lg border border-border bg-card p-6 space-y-4 w-80 shadow-lg">
            <h3 className="text-sm font-semibold">Delete Profile?</h3>
            <p className="text-xs text-muted-foreground">
              This action cannot be undone.
            </p>
            <div className="flex gap-2 justify-end">
              <Button
                variant="outline"
                size="sm"
                onClick={() => setDeleteTarget(null)}
              >
                Cancel
              </Button>
              <Button
                variant="destructive"
                size="sm"
                onClick={() => void handleDelete(deleteTarget)}
              >
                Delete
              </Button>
            </div>
          </div>
        </div>
      )}

      {/* Create/Edit modal */}
      {showCreate && (
        <ProfileModal
          profile={editProfile}
          onClose={() => {
            setShowCreate(false);
            setEditProfile(null);
          }}
          onSaved={() => {
            setShowCreate(false);
            setEditProfile(null);
            void loadProfiles();
          }}
        />
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Profile Create/Edit Modal
// ---------------------------------------------------------------------------
function ProfileModal({
  profile,
  onClose,
  onSaved,
}: {
  profile: MotorProfile | null;
  onClose: () => void;
  onSaved: () => void;
}) {
  const isEdit = profile !== null;
  const [name, setName] = useState(profile?.name ?? "New Motor");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [geometry, setGeometry] = useState<MotorGeometry>(
    profile?.geometry ?? {
      D_motor_mm: 106,
      L_motor_mm: 48.85,
      m_motor_g: 2800,
      t_housing_mm: 10.5,
      L_housing_mm: null,
      m_housing_g: 600,
      t_mold_mm: 0.5,
      f_copper: 0.35,
    },
  );

  async function handleSave() {
    setSaving(true);
    setError(null);
    try {
      if (isEdit && profile) {
        await profilesApi.update(profile.id, { name, geometry });
      } else {
        await profilesApi.create({ name, geometry, iron_loss_mode: "simple" });
      }
      onSaved();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Save failed");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
      <div className="rounded-lg border border-border bg-card p-6 space-y-4 w-full max-w-lg max-h-[90vh] overflow-y-auto shadow-lg">
        <h3 className="text-sm font-semibold">
          {isEdit ? "Edit Profile" : "Create Profile"}
        </h3>

        {error && (
          <p className="text-xs text-destructive">{error}</p>
        )}

        <div className="space-y-1">
          <label className="text-xs text-muted-foreground">Name</label>
          <input
            type="text"
            className="w-full rounded-md border border-input bg-background px-3 py-1.5 text-sm"
            value={name}
            onChange={(e) => setName(e.target.value)}
          />
        </div>

        <GeometryFields geometry={geometry} onChange={setGeometry} />

        <div className="flex gap-2 justify-end pt-2">
          <Button variant="outline" size="sm" onClick={onClose}>
            Cancel
          </Button>
          <Button size="sm" disabled={saving} onClick={() => void handleSave()}>
            {saving ? "Saving..." : isEdit ? "Update" : "Create"}
          </Button>
        </div>
      </div>
    </div>
  );
}

function GeometryFields({
  geometry,
  onChange,
}: {
  geometry: MotorGeometry;
  onChange: (g: MotorGeometry) => void;
}) {
  const fields: { key: keyof MotorGeometry; label: string; unit: string }[] = [
    { key: "D_motor_mm", label: "Stator Diameter", unit: "mm" },
    { key: "L_motor_mm", label: "Stator Length", unit: "mm" },
    { key: "m_motor_g", label: "Motor Mass", unit: "g" },
    { key: "t_housing_mm", label: "Housing Thickness", unit: "mm" },
    { key: "L_housing_mm", label: "Housing Length", unit: "mm" },
    { key: "m_housing_g", label: "Housing Mass", unit: "g" },
    { key: "t_mold_mm", label: "Mold Thickness", unit: "mm" },
    { key: "f_copper", label: "Copper Fill", unit: "" },
  ];

  return (
    <div className="space-y-2">
      <h4 className="text-xs font-semibold text-foreground">Geometry</h4>
      {fields.map(({ key, label, unit }) => (
        <div key={key} className="flex items-center gap-2">
          <label className="w-32 text-xs text-muted-foreground">{label}</label>
          <input
            type="number"
            step="any"
            className="flex-1 rounded-md border border-input bg-background px-2 py-1 text-sm font-mono tabular-nums"
            value={geometry[key] ?? ""}
            onChange={(e) => {
              const val =
                e.target.value === "" && key === "L_housing_mm"
                  ? null
                  : parseFloat(e.target.value);
              onChange({
                ...geometry,
                [key]:
                  key === "L_housing_mm"
                    ? (val as number | null)
                    : (val as number),
              });
            }}
          />
          {unit && (
            <span className="text-xs text-muted-foreground w-14">{unit}</span>
          )}
        </div>
      ))}
    </div>
  );
}
