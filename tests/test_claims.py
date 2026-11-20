import pytest

from app.claims import calculate_payout


def test_deductible_is_subtracted():
    assert calculate_payout(1000, 200, 5000) == 800


def test_payout_is_capped_at_coverage_limit():
    assert calculate_payout(10000, 200, 5000) == 5000


def test_payout_never_negative():
    assert calculate_payout(100, 200, 5000) == 0


def test_negative_claim_rejected():
    with pytest.raises(ValueError):
        calculate_payout(-1, 0, 5000)
