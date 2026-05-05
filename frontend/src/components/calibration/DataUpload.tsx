import { useState, useCallback } from "react";
import { filesApi } from "@/lib/api";
import type { FileUploadResponse, FileConditionSummary } from "@/types/data";
import { Upload, FileText, X } from "lucide-react";

interface DataUploadProps {
  fileType: "test_data" | "loss_map";
  fileId: string | null;
  onFileUploaded: (fileId: string, response: FileUploadResponse) => void;
  columns: string[];
  preview: Record<string, unknown>[];
  /** When true, allows selecting and uploading multiple files at once */
  multiple?: boolean;
  /** Uploaded file entries in multi-file mode */
  uploadedFiles?: FileUploadResponse[];
  /** Per-file condition summaries in multi-file mode */
  fileConditions?: Map<string, FileConditionSummary>;
  /** Remove a file from the multi-file list */
  onRemoveFile?: (fileId: string) => void;
}

function formatRange(
  range: [number | null, number | null],
  unit = "",
): string {
  const [lo, hi] = range;
  if (lo === null && hi === null) return "-";
  if (lo === null || hi === null) return `${lo ?? hi}${unit}`;
  return `${lo}-${hi}${unit}`;
}

export default function DataUpload({
  fileType,
  fileId,
  onFileUploaded,
  columns,
  preview,
  multiple = false,
  uploadedFiles = [],
  fileConditions,
  onRemoveFile,
}: DataUploadProps) {
  const [dragging, setDragging] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleFiles = useCallback(
    async (files: File[]) => {
      setUploading(true);
      setError(null);
      try {
        if (multiple && files.length > 1) {
          const responses = await filesApi.uploadBatch(files, fileType);
          for (const response of responses) {
            onFileUploaded(response.file_id, response);
          }
        } else {
          // Single file path (also used as fallback for single-file in multi mode)
          const response = await filesApi.upload(files[0], fileType);
          onFileUploaded(response.file_id, response);
        }
      } catch (err: unknown) {
        const msg =
          err instanceof Error ? err.message : "Upload failed";
        setError(msg);
      } finally {
        setUploading(false);
      }
    },
    [fileType, onFileUploaded, multiple],
  );

  function handleDrop(e: React.DragEvent) {
    e.preventDefault();
    setDragging(false);
    const fileList = Array.from(e.dataTransfer.files);
    if (fileList.length > 0) void handleFiles(fileList);
  }

  function handleInputChange(e: React.ChangeEvent<HTMLInputElement>) {
    const fileList = e.target.files ? Array.from(e.target.files) : [];
    if (fileList.length > 0) void handleFiles(fileList);
    // Reset input so the same file can be re-selected
    e.target.value = "";
  }

  // Multi-file mode: show uploaded files table with conditions
  if (multiple && uploadedFiles.length > 0) {
    return (
      <div className="space-y-3">
        <div className="flex items-center gap-2 text-sm text-foreground">
          <FileText className="size-4 text-green-600" />
          <span className="font-medium">
            {uploadedFiles.length} file{uploadedFiles.length !== 1 ? "s" : ""} uploaded
          </span>
        </div>

        {/* File conditions table */}
        {fileConditions && fileConditions.size > 0 && (
          <div className="overflow-x-auto rounded-md border border-border">
            <table className="w-full text-xs">
              <thead>
                <tr className="border-b border-border bg-muted/50">
                  <th className="px-2 py-1.5 text-left font-mono text-muted-foreground">File</th>
                  <th className="px-2 py-1.5 text-right font-mono text-muted-foreground">Rows</th>
                  <th className="px-2 py-1.5 text-right font-mono text-muted-foreground">I (A)</th>
                  <th className="px-2 py-1.5 text-right font-mono text-muted-foreground">RPM</th>
                  <th className="px-2 py-1.5 text-right font-mono text-muted-foreground">T_amb</th>
                  <th className="px-2 py-1.5 text-right font-mono text-muted-foreground">T_coil</th>
                  <th className="px-2 py-1.5 text-right font-mono text-muted-foreground">Duration</th>
                  <th className="px-2 py-1.5 text-center font-mono text-muted-foreground" />
                </tr>
              </thead>
              <tbody>
                {uploadedFiles.map((f) => {
                  const cond = fileConditions.get(f.file_id);
                  return (
                    <tr key={f.file_id} className="border-b border-border/50">
                      <td className="px-2 py-1 font-mono truncate max-w-[180px]">
                        {f.filename}
                      </td>
                      <td className="px-2 py-1 text-right font-mono tabular-nums">
                        {cond?.rows ?? f.rows}
                      </td>
                      <td className="px-2 py-1 text-right font-mono tabular-nums">
                        {cond ? formatRange(cond.I_range, "") : "-"}
                      </td>
                      <td className="px-2 py-1 text-right font-mono tabular-nums">
                        {cond ? formatRange(cond.rpm_range, "") : "-"}
                      </td>
                      <td className="px-2 py-1 text-right font-mono tabular-nums">
                        {cond?.T_amb_mean != null ? `${cond.T_amb_mean}` : "-"}
                      </td>
                      <td className="px-2 py-1 text-right font-mono tabular-nums">
                        {cond ? formatRange(cond.T_coil_range, "") : "-"}
                      </td>
                      <td className="px-2 py-1 text-right font-mono tabular-nums">
                        {cond?.duration_s != null ? `${cond.duration_s}s` : "-"}
                      </td>
                      <td className="px-2 py-1 text-center">
                        {onRemoveFile && (
                          <button
                            type="button"
                            className="inline-flex items-center justify-center rounded p-0.5 text-muted-foreground hover:text-destructive hover:bg-destructive/10 transition-colors"
                            onClick={() => onRemoveFile(f.file_id)}
                            aria-label={`Remove ${f.filename}`}
                          >
                            <X className="size-3.5" />
                          </button>
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
              <tfoot>
                <tr className="bg-muted/30">
                  <td className="px-2 py-1 font-medium">Total</td>
                  <td className="px-2 py-1 text-right font-mono tabular-nums font-medium">
                    {uploadedFiles.reduce((sum, f) => {
                      const cond = fileConditions?.get(f.file_id);
                      return sum + (cond?.rows ?? f.rows);
                    }, 0)}
                  </td>
                  <td colSpan={6} />
                </tr>
              </tfoot>
            </table>
          </div>
        )}

        {/* Fallback: show columns/preview when no conditions */}
        {(!fileConditions || fileConditions.size === 0) && columns.length > 0 && (
          <div className="rounded-md border border-border p-3">
            <p className="text-xs font-semibold text-muted-foreground mb-1">
              Detected Columns
            </p>
            <div className="flex flex-wrap gap-1">
              {columns.map((col) => (
                <span
                  key={col}
                  className="rounded bg-muted px-1.5 py-0.5 text-xs font-mono"
                >
                  {col}
                </span>
              ))}
            </div>
          </div>
        )}

        {/* Add more files button */}
        <label className="cursor-pointer">
          <span className="inline-flex items-center justify-center rounded-md border border-input bg-background px-3 py-1 text-xs font-medium hover:bg-muted">
            {uploading ? "Uploading..." : "Add More Files"}
            <input
              type="file"
              accept=".csv,.xlsx,.xls"
              multiple
              className="hidden"
              onChange={handleInputChange}
            />
          </span>
        </label>
        {error && <p className="text-xs text-destructive">{error}</p>}
      </div>
    );
  }

  // Single-file mode: show uploaded file info
  if (!multiple && fileId) {
    return (
      <div className="space-y-3">
        <div className="flex items-center gap-2 text-sm text-foreground">
          <FileText className="size-4 text-green-600" />
          <span className="font-medium">File uploaded</span>
        </div>

        {columns.length > 0 && (
          <div className="rounded-md border border-border p-3">
            <p className="text-xs font-semibold text-muted-foreground mb-1">
              Detected Columns
            </p>
            <div className="flex flex-wrap gap-1">
              {columns.map((col) => (
                <span
                  key={col}
                  className="rounded bg-muted px-1.5 py-0.5 text-xs font-mono"
                >
                  {col}
                </span>
              ))}
            </div>
          </div>
        )}

        {preview.length > 0 && (
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead>
                <tr className="border-b border-border">
                  {Object.keys(preview[0]).map((col) => (
                    <th
                      key={col}
                      className="px-2 py-1 text-left font-mono text-muted-foreground"
                    >
                      {col}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {preview.map((row, i) => (
                  <tr key={i} className="border-b border-border/50">
                    {Object.values(row).map((val, j) => (
                      <td key={j} className="px-2 py-1 font-mono tabular-nums">
                        {String(val)}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    );
  }

  // Drop zone (shared for both modes)
  return (
    <div className="space-y-2">
      <div
        onDragOver={(e) => {
          e.preventDefault();
          setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={handleDrop}
        className={`flex flex-col items-center justify-center rounded-lg border-2 border-dashed p-8 transition-colors ${
          dragging
            ? "border-primary bg-primary/5"
            : "border-border hover:border-primary/50"
        }`}
      >
        <Upload className="size-8 text-muted-foreground mb-2" />
        <p className="text-sm text-muted-foreground">
          {multiple
            ? "Drag & drop CSV or Excel files here"
            : "Drag & drop a CSV or Excel file here"}
        </p>
        <label className="mt-2 cursor-pointer">
          <span className="inline-flex items-center justify-center rounded-md border border-input bg-background px-3 py-1 text-xs font-medium hover:bg-muted disabled:pointer-events-none disabled:opacity-50">
            {uploading ? "Uploading..." : "Browse Files"}
            <input
              type="file"
              accept=".csv,.xlsx,.xls"
              multiple={multiple}
              className="hidden"
              onChange={handleInputChange}
            />
          </span>
        </label>
      </div>
      {error && <p className="text-xs text-destructive">{error}</p>}
    </div>
  );
}
