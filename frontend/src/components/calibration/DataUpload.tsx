import { useState, useCallback } from "react";
import { filesApi } from "@/lib/api";
import type { FileUploadResponse } from "@/types/data";
import { Upload, FileText } from "lucide-react";

interface DataUploadProps {
  fileType: "test_data" | "loss_map";
  fileId: string | null;
  onFileUploaded: (fileId: string, response: FileUploadResponse) => void;
  columns: string[];
  preview: Record<string, unknown>[];
}

export default function DataUpload({
  fileType,
  fileId,
  onFileUploaded,
  columns,
  preview,
}: DataUploadProps) {
  const [dragging, setDragging] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleFile = useCallback(
    async (file: File) => {
      setUploading(true);
      setError(null);
      try {
        const response = await filesApi.upload(file, fileType);
        onFileUploaded(response.file_id, response);
      } catch (err: unknown) {
        const msg =
          err instanceof Error ? err.message : "Upload failed";
        setError(msg);
      } finally {
        setUploading(false);
      }
    },
    [fileType, onFileUploaded],
  );

  function handleDrop(e: React.DragEvent) {
    e.preventDefault();
    setDragging(false);
    const file = e.dataTransfer.files[0];
    if (file) void handleFile(file);
  }

  function handleInputChange(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (file) void handleFile(file);
  }

  if (fileId) {
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
          Drag &amp; drop a CSV or Excel file here
        </p>
        <label className="mt-2 cursor-pointer">
          <span className="inline-flex items-center justify-center rounded-md border border-input bg-background px-3 py-1 text-xs font-medium hover:bg-muted disabled:pointer-events-none disabled:opacity-50">
            {uploading ? "Uploading..." : "Browse Files"}
            <input
              type="file"
              accept=".csv,.xlsx,.xls"
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
