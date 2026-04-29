import axios from "axios";
import type { AxiosResponse } from "axios";
import type {
  MotorProfile,
  MotorProfileCreate,
  MotorProfileUpdate,
  MotorProfileSummary,
  MotorGeometry,
  MaterialProps,
  GeometryPreview,
} from "@/types/motor";
import type {
  CalibRequest,
  CalibResult,
  CalibProgressEvent,
} from "@/types/calibration";
import type {
  FileUploadResponse,
  FileColumnsResponse,
  ColumnMappingRequest,
  ColumnMappingResponse,
  SteadyStateRequest,
  SteadyStateResult,
  GridPredictionRequest,
  GridPredictionResult,
  ExportRequest,
} from "@/types/data";

const api = axios.create({
  baseURL: "/api",
  headers: { "Content-Type": "application/json" },
});

// Helper to extract data from axios response
function unwrap<T>(response: AxiosResponse<T>): T {
  return response.data;
}

// ---------------------------------------------------------------------------
// Profiles API
// ---------------------------------------------------------------------------
export const profilesApi = {
  list: () =>
    api
      .get<MotorProfileSummary[]>("/profiles")
      .then((r) => r.data),

  get: (id: string) =>
    api
      .get<MotorProfile>(`/profiles/${id}`)
      .then((r) => r.data),

  create: (data: MotorProfileCreate) =>
    api
      .post<MotorProfile>("/profiles", data)
      .then((r) => r.data),

  update: (id: string, data: MotorProfileUpdate) =>
    api
      .put<MotorProfile>(`/profiles/${id}`, data)
      .then((r) => r.data),

  delete: (id: string) =>
    api.delete(`/profiles/${id}`).then((r) => r.status === 204),

  copy: (id: string) =>
    api
      .post<MotorProfile>(`/profiles/${id}/copy`)
      .then((r) => r.data),

  computeGeometry: (geometry: MotorGeometry, material?: MaterialProps) =>
    api
      .post<GeometryPreview>("/profiles/compute-geometry", {
        ...geometry,
        ...(material ? { material } : {}),
      })
      .then((r) => r.data),
};

// ---------------------------------------------------------------------------
// Files API
// ---------------------------------------------------------------------------
export const filesApi = {
  upload: async (
    file: File,
    type: "test_data" | "loss_map",
  ): Promise<FileUploadResponse> => {
    const form = new FormData();
    form.append("file", file);
    form.append("type", type);
    const response = await api.post<FileUploadResponse>(
      "/files/upload",
      form,
      { headers: { "Content-Type": "multipart/form-data" } },
    );
    return response.data;
  },

  getColumns: (fileId: string) =>
    api
      .get<FileColumnsResponse>(`/files/${fileId}/columns`)
      .then((r) => r.data),

  mapColumns: (fileId: string, mapping: ColumnMappingRequest) =>
    api
      .post<ColumnMappingResponse>(`/files/${fileId}/map-columns`, mapping)
      .then((r) => r.data),

  delete: (fileId: string) =>
    api.delete(`/files/${fileId}`).then((r) => r.status === 204),
};

// ---------------------------------------------------------------------------
// Calibration API
// ---------------------------------------------------------------------------
export const calibrationApi = {
  start: (req: CalibRequest) =>
    api
      .post<{ job_id: string }>("/calibration/start", req)
      .then((r) => r.data.job_id),

  /**
   * Opens an SSE connection for calibration progress events.
   * Returns a cleanup function to close the connection.
   */
  streamProgress: (
    jobId: string,
    onEvent: (event: CalibProgressEvent) => void,
    onError: (error: Event) => void,
  ): (() => void) => {
    const es = new EventSource(`/api/calibration/${jobId}/stream`);

    es.onmessage = (e: MessageEvent) => {
      try {
        const parsed: CalibProgressEvent = JSON.parse(e.data as string);
        onEvent(parsed);

        if (parsed.type === "done" || parsed.type === "error") {
          es.close();
        }
      } catch {
        // Ignore malformed SSE data
      }
    };

    es.onerror = (e: Event) => {
      onError(e);
      es.close();
    };

    return () => es.close();
  },

  getResult: (jobId: string) =>
    api
      .get<CalibResult>(`/calibration/${jobId}/result`)
      .then((r) => r.data),
};

// ---------------------------------------------------------------------------
// Prediction API
// ---------------------------------------------------------------------------
export const predictionApi = {
  steadyState: (req: SteadyStateRequest) =>
    api
      .post<SteadyStateResult>("/prediction/steady-state", req)
      .then((r) => r.data),

  grid: (req: GridPredictionRequest) =>
    api
      .post<GridPredictionResult>("/prediction/grid", req)
      .then((r) => r.data),
};

// ---------------------------------------------------------------------------
// Export API
// ---------------------------------------------------------------------------
export const exportApi = {
  /** Downloads an Excel file for the given export request. */
  excel: async (req: ExportRequest): Promise<void> => {
    const response = await api.post("/export/excel", req, {
      responseType: "blob",
    });
    // Extract filename from Content-Disposition header
    const disposition = response.headers["content-disposition"];
    let filename = "export.xlsx";
    if (typeof disposition === "string") {
      const match = disposition.match(/filename="?([^";\n]+)"?/);
      if (match) {
        filename = match[1];
      }
    }
    const url = URL.createObjectURL(response.data as Blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  },
};

export { unwrap };
export default api;
