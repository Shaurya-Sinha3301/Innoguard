class WorkflowError(Exception):
    """Base class for rule violations in the invoice workflow."""


class InvoiceNotFound(WorkflowError):
    pass


class IllegalTransition(WorkflowError):
    pass


class StaleVersion(WorkflowError):
    """The caller acted on an older version of the invoice than the one now on file."""


class NotApproved(WorkflowError):
    """Posting was attempted without a valid approval for the current invoice version."""
