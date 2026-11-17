import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { api } from "../api";
import { Button, Card, CardHeader, Empty, ErrorNote, td, th } from "../components/ui";
import { when } from "../format";

export default function FailedJobs() {
  const queryClient = useQueryClient();
  const jobs = useQuery({ queryKey: ["failed-jobs"], queryFn: api.failedJobs, refetchInterval: 5000 });
  const replay = useMutation({
    mutationFn: (invoiceId: string) => api.replay(invoiceId),
    onSuccess: () => queryClient.invalidateQueries(),
  });

  return (
    <Card>
      <CardHeader title="Failed jobs (dead letter)" />
      <div className="p-4 empty:hidden">
        <ErrorNote error={jobs.error ?? replay.error} />
      </div>
      {jobs.data && jobs.data.length === 0 && <Empty>No failed jobs.</Empty>}
      {jobs.data && jobs.data.length > 0 && (
        <div className="overflow-x-auto">
          <table className="w-full">
            <thead className="border-b border-border">
              <tr>
                <th className={th}>Invoice</th>
                <th className={th}>Task</th>
                <th className={th}>Error</th>
                <th className={`${th} text-right`}>Attempts</th>
                <th className={th}>When</th>
                <th className={th} />
              </tr>
            </thead>
            <tbody>
              {jobs.data.map((job) => (
                <tr key={job.id} className="border-b border-border last:border-0">
                  <td className={td}>
                    {job.invoice_id ? (
                      <Link className="text-primary hover:underline" to={`/invoices/${job.invoice_id}`}>
                        {job.invoice_id.slice(0, 8)}
                      </Link>
                    ) : (
                      "—"
                    )}
                  </td>
                  <td className={td}>{job.task}</td>
                  <td className={`${td} max-w-md`}>{job.error}</td>
                  <td className={`${td} text-right tabular-nums`}>{job.attempts}</td>
                  <td className={`${td} text-muted-foreground`}>{when(job.created_at)}</td>
                  <td className={td}>
                    {job.invoice_id && (
                      <Button
                        variant="secondary"
                        disabled={replay.isPending}
                        onClick={() => replay.mutate(job.invoice_id!)}
                      >
                        Replay
                      </Button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </Card>
  );
}
