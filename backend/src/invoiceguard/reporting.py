"""Operational metrics for the dashboard, computed from stored events.

These describe what the running system did. They are not accuracy figures: accuracy needs
ground truth and comes from the evaluation harness in eval/.
"""

from decimal import Decimal
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

_DECISION_STATES = ("AUTO_APPROVED", "NEEDS_REVIEW", "REJECTED")


def _ratio(part: int, whole: int) -> Decimal | None:
    return None if whole == 0 else (Decimal(part) / Decimal(whole)).quantize(Decimal("0.0001"))


def summary(session: Session, pack: str | None = None) -> dict[str, Any]:
    """Operational metrics, for one pack or (pack None) for everything."""
    scope = {"pack": pack}
    by_status = dict(
        session.execute(
            text(
                "SELECT status, count(*) FROM cases "
                "WHERE (CAST(:pack AS text) IS NULL OR pack_id = :pack) GROUP BY status"
            ),
            scope,
        ).all()
    )

    first_decisions = dict(
        session.execute(
            text(
                """
                SELECT decision, count(*) FROM (
                    SELECT DISTINCT ON (case_id) case_id, payload->>'to' AS decision
                    FROM audit_events
                    WHERE event_type = 'invoice.state_changed'
                      AND payload->>'to' IN ('AUTO_APPROVED', 'NEEDS_REVIEW', 'REJECTED')
                      AND (CAST(:pack AS text) IS NULL
                           OR case_id IN (SELECT id FROM cases WHERE pack_id = :pack))
                    ORDER BY case_id, id
                ) first_decision
                GROUP BY decision
                """
            ),
            scope,
        ).all()
    )
    decided = sum(first_decisions.values())

    exceptions = [
        {"reason": reason, "count": count}
        for reason, count in session.execute(
            text(
                """
                SELECT reason, count(*) AS n
                FROM audit_events,
                     jsonb_array_elements_text(coalesce(payload->'reasons', '[]'::jsonb)) AS reason
                WHERE event_type = 'invoice.state_changed' AND payload->>'to' = 'NEEDS_REVIEW'
                  AND (CAST(:pack AS text) IS NULL
                       OR case_id IN (SELECT id FROM cases WHERE pack_id = :pack))
                GROUP BY reason ORDER BY n DESC, reason
                """
            ),
            scope,
        ).all()
    ]

    review = session.execute(
        text(
            """
            WITH entered AS (
                SELECT case_id, min(created_at) AS at
                FROM audit_events
                WHERE event_type = 'invoice.state_changed' AND payload->>'to' = 'NEEDS_REVIEW'
                  AND (CAST(:pack AS text) IS NULL
                       OR case_id IN (SELECT id FROM cases WHERE pack_id = :pack))
                GROUP BY case_id
            ), decided AS (
                SELECT case_id, min(created_at) AS at
                FROM approvals WHERE reviewer <> 'system'
                  AND (CAST(:pack AS text) IS NULL
                       OR case_id IN (SELECT id FROM cases WHERE pack_id = :pack))
                GROUP BY case_id
            )
            SELECT count(*),
                   percentile_cont(0.5) WITHIN GROUP (
                       ORDER BY extract(epoch FROM decided.at - entered.at)
                   )
            FROM entered JOIN decided USING (case_id)
            """
        ),
        scope,
    ).one()
    overrides = session.execute(
        text(
            "SELECT count(*) FROM audit_events WHERE event_type = 'invoice.edited' "
            "AND (CAST(:pack AS text) IS NULL "
            "OR case_id IN (SELECT id FROM cases WHERE pack_id = :pack))"
        ),
        scope,
    ).scalar_one()

    llm = [
        {
            "provider": provider,
            "model": model,
            "calls": calls,
            "total_cost_usd": total,
            "cost_per_request_usd": per_call,
            "p50_latency_ms": p50,
            "p95_latency_ms": p95,
            "avg_tokens_per_second": tps,
        }
        for provider, model, calls, total, per_call, p50, p95, tps in session.execute(
            text(
                """
                SELECT provider, model, count(*), sum(cost_usd), avg(cost_usd),
                       percentile_cont(0.5) WITHIN GROUP (ORDER BY latency_ms),
                       percentile_cont(0.95) WITHIN GROUP (ORDER BY latency_ms),
                       avg(tokens_per_second)
                FROM llm_calls WHERE (CAST(:pack AS text) IS NULL OR case_id IN
                    (SELECT id FROM cases WHERE pack_id = :pack))
                GROUP BY provider, model ORDER BY provider, model
                """
            ),
            scope,
        ).all()
    ]

    health = session.execute(
        text(
            """
            SELECT (SELECT count(*) FROM failed_jobs WHERE status = 'FAILED'),
                   (SELECT count(*) FROM outbox WHERE status = 'PENDING')
            """
        )
    ).one()

    return {
        "invoices_by_status": by_status,
        "decisions": {
            "decided": decided,
            "auto_approved": first_decisions.get("AUTO_APPROVED", 0),
            "needs_review": first_decisions.get("NEEDS_REVIEW", 0),
            "rejected": first_decisions.get("REJECTED", 0),
            "straight_through_rate": _ratio(first_decisions.get("AUTO_APPROVED", 0), decided),
            "review_rate": _ratio(first_decisions.get("NEEDS_REVIEW", 0), decided),
        },
        "exceptions": exceptions,
        "human_workload": {
            "reviewed": review[0],
            "median_review_seconds": None if review[1] is None else round(review[1], 1),
            "edits": overrides,
        },
        "llm": llm,
        "operations": {"open_failed_jobs": health[0], "outbox_pending": health[1]},
    }
