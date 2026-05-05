import { useState, useCallback } from "react";
import { compressorApi } from "@/lib/api";
import type { CompressorUploadResponse, CompressorSheetInfo } from "@/types/compressor";
import { Upload, FileSpreadsheet, AlertCircle, CheckCircle2 } from "lucide-react";

interface CompressorUploadProps {
  onUploaded: (response: CompressorUploadResponse) => void;
  /** Current uploaded filename, if any */
  filename: string | null;
}

export default function CompressorUpload({ onUploaded, filename }: CompressorUploadProps) {
  const [dragging, setDragging] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [uploadResult, setUploadResult] = useState<CompressorUploadResponse | null>(null);

  const handleFile = useCallback(
    async (file: File) => {
      setUploading(true);
      setError(null);
      try {
        const response = await compressorApi.upload(file);
        setUploadResult(response);
        onUploaded(response);
      } catch (err: unknown) {
        const msg = err instanceof Error ? err.message : "Upload failed";
        setError(msg);
      } finally {
        setUploading(false);
      }
    },
    [onUploaded],
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
    e.target.value = "";
  }

  // Show upload result if available
  if (uploadResult || filename) {
    const result = uploadResult;
    return (
      <div className="space-y-3">
        <div className="flex items-center gap-2 text-sm text-foreground">
          <FileSpreadsheet className="size-4 text-green-600" />
          <span className="font-medium">
            {result?.filename ?? filename ?? "File uploaded"}
          </span>
        </div>

        {result && (
          <>
            {/* Summary stats */}
            <div className="grid grid-cols-3 gap-2">
              <SummaryCard
                label="Total Points"
                value={String(result.total_points)}
              />
              <SummaryCard
                label="Valid Sheets"
                value={String(result.valid_sheets)}
                accent={result.valid_sheets > 0 ? "green" : "red"}
              />
              <SummaryCard
                label="Invalid Sheets"
                value={String(result.invalid_sheets)}
                accent={result.invalid_sheets > 0 ? "red" : "green"}
              />
            </div>

            {/* Per-sheet details */}
            <div className="overflow-x-auto rounded-md border border-border">
              <table className="w-full text-xs">
                <thead>
                  <tr className="border-b border-border bg-muted/50">
                    <th className="px-2 py-1.5 text-left font-mono text-muted-foreground">Sheet</th>
                    <th className="px-2 py-1.5 text-left font-mono text-muted-foreground">Variant</th>
                    <th className="px-2 py-1.5 text-right font-mono text-muted-foreground">Points</th>
                    <th className="px-2 py-1.5 text-left font-mono text-muted-foreground">Status</th>
                    <th className="px-2 py-1.5 text-left font-mono text-muted-foreground">Missing</th>
                  </tr>
                </thead>
                <tbody>
                  {result.sheets.map((sheet) => (
                    <SheetRow key={sheet.sheet_name} sheet={sheet} />
                  ))}
                </tbody>
              </table>
            </div>
          </>
        )}

        {/* Re-upload button */}
        <label className="cursor-pointer">
          <span className="inline-flex items-center justify-center rounded-md border border-input bg-background px-3 py-1 text-xs font-medium hover:bg-muted">
            {uploading ? "Uploading..." : "Upload Different File"}
            <input
              type="file"
              accept=".xlsx,.xls"
              className="hidden"
              onChange={handleInputChange}
            />
          </span>
        </label>
        {error && <p className="text-xs text-destructive">{error}</p>}
      </div>
    );
  }

  // Drop zone
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
          Drag & drop a multi-sheet Excel file here
        </p>
        <p className="text-xs text-muted-foreground mt-1">
          Supports .xlsx and .xls files with compressor test data
        </p>
        <label className="mt-2 cursor-pointer">
          <span className="inline-flex items-center justify-center rounded-md border border-input bg-background px-3 py-1 text-xs font-medium hover:bg-muted">
            {uploading ? "Uploading..." : "Browse Files"}
            <input
              type="file"
              accept=".xlsx,.xls"
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

function SheetRow({ sheet }: { sheet: CompressorSheetInfo }) {
  const hasErrors = sheet.errors.length > 0 || sheet.columns_missing.length > 0;
  return (
    <tr className="border-b border-border/50">
      <td className="px-2 py-1 font-mono">{sheet.sheet_name}</td>
      <td className="px-2 py-1 font-mono text-muted-foreground">
        {sheet.variant_name ?? "-"}
      </td>
      <td className="px-2 py-1 text-right font-mono tabular-nums">
        {sheet.n_points}
      </td>
      <td className="px-2 py-1">
        {hasErrors ? (
          <span className="inline-flex items-center gap-1 text-destructive">
            <AlertCircle className="size-3" />
            <span className="text-xs">{sheet.errors.length} error{sheet.errors.length !== 1 ? "s" : ""}</span>
          </span>
        ) : (
          <span className="inline-flex items-center gap-1 text-green-600">
            <CheckCircle2 className="size-3" />
            <span className="text-xs">OK</span>
          </span>
        )}
      </td>
      <td className="px-2 py-1">
        {sheet.columns_missing.length > 0 ? (
          <div className="flex flex-wrap gap-0.5">
            {sheet.columns_missing.map((col) => (
              <span key={col} className="rounded bg-destructive/10 px-1 text-[10px] text-destructive">
                {col}
              </span>
            ))}
          </div>
        ) : (
          <span className="text-xs text-muted-foreground">-</span>
        )}
      </td>
    </tr>
  );
}

function SummaryCard({
  label,
  value,
  accent,
}: {
  label: string;
  value: string;
  accent?: "green" | "red";
}) {
  const colorClass =
    accent === "green"
      ? "text-green-600"
      : accent === "red"
        ? "text-destructive"
        : "text-foreground";
  return (
    <div className="rounded-md border border-border bg-card p-2">
      <p className="text-xs text-muted-foreground">{label}</p>
      <p className={`text-sm font-mono tabular-nums font-semibold ${colorClass}`}>
        {value}
      </p>
    </div>
  );
}
