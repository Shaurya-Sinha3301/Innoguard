import { useMutation } from "@tanstack/react-query";
import { useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api";
import { Button, Card, CardHeader, ErrorNote } from "../components/ui";

export default function Upload() {
  const [file, setFile] = useState<File | null>(null);
  const upload = useMutation({ mutationFn: (f: File) => api.upload(f) });

  return (
    <Card className="max-w-xl">
      <CardHeader title="Upload an invoice PDF" />
      <form
        className="space-y-3 p-4"
        onSubmit={(e) => {
          e.preventDefault();
          if (file) upload.mutate(file);
        }}
      >
        <p className="text-sm text-muted-foreground">
          PDF only, up to 5 MB. In the hosted demo, only the synthetic sample invoices have recorded extractions; other
          files go to failed jobs.
        </p>
        <input
          type="file"
          accept="application/pdf"
          aria-label="Invoice PDF"
          className="block w-full text-sm"
          onChange={(e) => setFile(e.target.files?.[0] ?? null)}
        />
        <Button type="submit" disabled={!file || upload.isPending}>
          {upload.isPending ? "Uploading…" : "Upload"}
        </Button>
        <ErrorNote error={upload.error} />
        {upload.data && (
          <p className="text-sm">
            Queued for extraction.{" "}
            <Link className="text-primary hover:underline" to={`/invoices/${upload.data.id}`}>
              Open the invoice
            </Link>
          </p>
        )}
      </form>
    </Card>
  );
}
