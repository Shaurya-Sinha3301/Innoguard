import pytest

from invoiceguard.workflow.errors import IllegalTransition
from invoiceguard.workflow.state_machine import (
    ALLOWED,
    POSTABLE,
    InvoiceState,
    assert_transition,
    can_transition,
)

S = InvoiceState


def test_every_state_has_a_transition_entry():
    assert set(ALLOWED) == set(InvoiceState)


@pytest.mark.parametrize("terminal", [S.POSTED, S.REJECTED])
def test_terminal_states_have_no_exits(terminal):
    assert ALLOWED[terminal] == frozenset()


@pytest.mark.parametrize(
    ("current", "target"),
    [
        (S.RECEIVED, S.VALIDATED),
        (S.MATCHED, S.AUTO_APPROVED),
        (S.NEEDS_REVIEW, S.APPROVED),
        (S.APPROVED, S.POSTING),
        (S.POSTING, S.POSTED),
        (S.POSTING, S.APPROVED),  # a failed post can be retried
        (S.APPROVED, S.NEEDS_REVIEW),  # a material edit voids the approval
        (S.FAILED, S.RECEIVED),  # replay from the dead-letter queue
    ],
)
def test_allowed_transitions(current, target):
    assert can_transition(current, target)
    assert_transition(current.value, target.value)


@pytest.mark.parametrize(
    ("current", "target"),
    [
        (S.NEEDS_REVIEW, S.POSTING),  # cannot post without approval
        (S.NEEDS_REVIEW, S.POSTED),
        (S.REJECTED, S.APPROVED),
        (S.POSTED, S.APPROVED),
        (S.RECEIVED, S.POSTED),
        (S.MATCHED, S.APPROVED),
    ],
)
def test_illegal_transitions_raise(current, target):
    assert not can_transition(current, target)
    with pytest.raises(IllegalTransition):
        assert_transition(current.value, target.value)


def test_only_approved_states_are_postable():
    assert POSTABLE == {S.APPROVED, S.AUTO_APPROVED}
