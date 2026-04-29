import { create } from "zustand";
import type { CalibResult, CalibProgressEvent } from "@/types/calibration";

// ---------------------------------------------------------------------------
// UI Slice
// ---------------------------------------------------------------------------
interface UiSlice {
  activePage: "calibration" | "prediction" | "profiles";
  sidebarCollapsed: boolean;
  setActivePage: (page: UiSlice["activePage"]) => void;
  toggleSidebar: () => void;
}

// ---------------------------------------------------------------------------
// Profile Slice
// ---------------------------------------------------------------------------
interface ProfileSlice {
  currentProfileId: string | null;
  setCurrentProfile: (id: string | null) => void;
}

// ---------------------------------------------------------------------------
// Calibration Slice
// ---------------------------------------------------------------------------
type CalibStatus = "idle" | "running" | "done" | "error";

interface CalibrationSlice {
  testFileId: string | null;
  lossMapFileId: string | null;
  columnMapping: Record<string, string>;
  calibJobId: string | null;
  calibStatus: CalibStatus;
  calibProgress: CalibProgressEvent[];
  calibResult: CalibResult | null;
  calibError: string | null;

  setTestFile: (id: string | null) => void;
  setLossMapFile: (id: string | null) => void;
  setColumnMapping: (mapping: Record<string, string>) => void;
  startCalib: (jobId: string) => void;
  updateProgress: (event: CalibProgressEvent) => void;
  finishCalib: (result: CalibResult) => void;
  errorCalib: (message: string) => void;
  resetCalib: () => void;
}

// ---------------------------------------------------------------------------
// Combined Store
// ---------------------------------------------------------------------------
type AppStore = UiSlice & ProfileSlice & CalibrationSlice;

const initialState = {
  // UI
  activePage: "calibration" as const,
  sidebarCollapsed: false,

  // Profile
  currentProfileId: null as string | null,

  // Calibration
  testFileId: null as string | null,
  lossMapFileId: null as string | null,
  columnMapping: {} as Record<string, string>,
  calibJobId: null as string | null,
  calibStatus: "idle" as CalibStatus,
  calibProgress: [] as CalibProgressEvent[],
  calibResult: null as CalibResult | null,
  calibError: null as string | null,
};

export const useAppStore = create<AppStore>()((set) => ({
  ...initialState,

  // UI actions
  setActivePage: (page) => set({ activePage: page }),
  toggleSidebar: () => set((s) => ({ sidebarCollapsed: !s.sidebarCollapsed })),

  // Profile actions
  setCurrentProfile: (id) => set({ currentProfileId: id }),

  // Calibration actions
  setTestFile: (id) => set({ testFileId: id }),
  setLossMapFile: (id) => set({ lossMapFileId: id }),
  setColumnMapping: (mapping) => set({ columnMapping: mapping }),

  startCalib: (jobId) =>
    set({
      calibJobId: jobId,
      calibStatus: "running",
      calibProgress: [],
      calibResult: null,
      calibError: null,
    }),

  updateProgress: (event) =>
    set((s) => ({
      calibProgress: [...s.calibProgress, event],
    })),

  finishCalib: (result) =>
    set({
      calibStatus: "done",
      calibResult: result,
    }),

  errorCalib: (message) =>
    set({
      calibStatus: "error",
      calibError: message,
    }),

  resetCalib: () =>
    set({
      calibJobId: null,
      calibStatus: "idle",
      calibProgress: [],
      calibResult: null,
      calibError: null,
      testFileId: null,
      lossMapFileId: null,
      columnMapping: {},
    }),
}));
