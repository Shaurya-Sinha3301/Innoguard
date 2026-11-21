import { useMutation } from "@tanstack/react-query";
import { FileUp } from "lucide-react";
import { useRef, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api";
import { Button, cx, ErrorNote, Module } from "../components/ui";

const MAX_BYTES = 5 * 1024 * 1024;

export default function Upload() {
  const [file, setFile] = useState<File | null>(null);
  const [problem, setProblem] = useState<string | null>(null);
  const [dragging, setDragging] = useState(false);
  const input = useRef<HTMLInputElement>(null);
  const upload = useMutation({ mutationFn: (f: File) => api.upload(f) });

  function choose(f: File | undefined) {
    upload.reset();
    if (!f) return;
    if (f.type !== "application/pdf" && !f.name.toLowerCase().endsWith(".pdf")) {
      setProblem("Only PDF files can be uploaded.");
      return setFile(null);
    }
    if (f.size > MAX_BYTES) {
      setProblem("That file is larger than the 5 MB limit.");
      return setFile(null);
    }
    setProblem(null);
    setFile(f);
  }

  return (
    <div className="grid gap-4 lg:grid-cols-12">
      <Module title="Upload an invoice" className="lg:col-span-7" bodyClassName="space-y-3 p-3">
        <div
          onDragOver={(e) => {
            e.preventDefault();
            setDragging(true);
          }}
          onDragLeave={() => setDragging(false)}
          onDrop={(e) => {
            e.preventDefault();
            setDragging(false);
            choose(e.dataTransfer.files[0]);
          }}
          className={cx(
            "flex flex-col items-center gap-2 rounded-xl border border-dashed px-4 py-12 text-center",
            dragging ? "border-accent bg-fill" : "border-line",
          )}
        >
          <FileUp aria-hidden className="h-6 w-6 text-ink-2" />
          <p className="text-sm">
            Drop a PDF here, or{" "}
            <button type="button" className="font-semibold underline underline-offset-4" onClick={() => input.current?.click()}>
              choose a file
            </button>
          </p>
          <p className="text-xs text-ink-2">PDF only, up to 5 MB.</p>
          <input
            ref={input}
            type="file"
            accept="application/pdf"
            className="sr-only"
            aria-label="Invoice PDF"
            onChange={(e) => choose(e.target.files?.[0])}
          />
        </div>
        {file && (
          <p className="text-sm">
            Selected: <span className="font-mono">{file.name}</span> <span className="text-ink-2">({Math.ceil(file.size / 1024)} KB)</span>
          </p>
        )}
        <div className="flex items-center gap-2">
          <Button disabled={!file || upload.isPending} onClick={() => file && upload.mutate(file)}>
            {upload.isPending ? "Uploading…" : "Upload for extraction"}
          </Button>
        </div>
        <ErrorNote error={problem ? new Error(problem) : upload.error} />
        {upload.data && (
          <p className="border border-green/40 bg-green-tint px-3 py-2 text-sm text-green">
            Queued for extraction.{" "}
            <Link className="font-semibold underline underline-offset-4" to={`/invoices/${upload.data.id}`}>
              Follow it
            </Link>
          </p>
        )}
      </Module>
      <Module title="What happens next" className="lg:col-span-5" bodyClassName="space-y-2 p-3 text-sm text-ink-2">
        <p>The upload and its extraction job are saved together, so a document is never lost even if the queue is down.</p>
        <p>
          The hosted demo runs in replay mode: only the synthetic sample invoices have recorded extractions. Any other PDF
          will end up in Failed jobs, which shows that path working.
        </p>
      </Module>
    </div>
  );
}
