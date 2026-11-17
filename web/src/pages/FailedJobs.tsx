import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { RotateCcw } from "lucide-react";
import { Link } from "react-router-dom";
import { api } from "../api";
import { Button, Empty, ErrorNote, Module, num, Row, SkeletonRows, Table, td, th } from "../components/ui";
import { when } from "../format";

export default function FailedJobs() {
  const queryClient = useQueryClient();
  const jobs = useQuery({ queryKey: ["failed-jobs"], queryFn: api.failedJobs, refetchInterval: 5000 });
  const replay = useMutation({
    mutationFn: (invoiceId: string) => api.replay(invoiceId),
    onSuccess: () => queryClient.invalidateQueries(),
  });

  return (
    <div className="grid gap-2 lg:grid-cols-12">
      <Module title="Failed jobs" count={jobs.data?.length} alert className="lg:col-span-9">
        <ErrorNote error={jobs.error ?? replay.error} />
        {jobs.isLoading && <SkeletonRows rows={4} cols={5} />}
        {jobs.data?.length === 0 && (
          <Empty title="No failed jobs">Every uploaded document was read, or is still being read.</Empty>
        )}
        {jobs.data && jobs.data.length > 0 && (
          <Table label="Jobs that ran out of attempts">
            <thead>
              <tr>
                <th className={th}>Invoice</th>
                <th className={th}>Task</th>
                <th className={th}>Error</th>
                <th className={`${th} text-right`}>Attempts</th>
                <th className={th}>Failed at</th>
                <th className={th}>
                  <span className="sr-only">Action</span>
                </th>
              </tr>
            </thead>
            <tbody>
              {jobs.data.map((job) => (
                <Row key={job.id}>
                  <td className={td}>
                    {job.invoice_id ? (
                      <Link className="font-mono text-[13px] underline decoration-line underline-offset-4 hover:decoration-red" to={`/invoices/${job.invoice_id}`}>
                        {job.invoice_id.slice(0, 8)}
                      </Link>
                    ) : (
                      "—"
                    )}
                  </td>
                  <td className={td}>{job.task}</td>
                  <td className={`${td} max-w-md whitespace-normal text-red`}>{job.error}</td>
                  <td className={`${td} ${num}`}>{job.attempts}</td>
                  <td className={`${td} text-ink-2`}>{when(job.created_at)}</td>
                  <td className={td}>
                    {job.invoice_id && (
                      <Button variant="secondary" disabled={replay.isPending} onClick={() => replay.mutate(job.invoice_id!)}>
                        <RotateCcw aria-hidden className="h-3.5 w-3.5" /> Replay
                      </Button>
                    )}
                  </td>
                </Row>
              ))}
            </tbody>
          </Table>
        )}
      </Module>
      <Module title="When a job fails" className="lg:col-span-3" bodyClassName="space-y-2 p-3 text-sm text-ink-2">
        <p>Rate limits and network errors are retried with backoff. A job lands here only when it runs out of attempts, or when the model refuses or returns unusable output.</p>
        <p>Fix the cause, then replay. Replaying is safe: the job checks the invoice state first and never extracts twice.</p>
      </Module>
    </div>
  );
}
