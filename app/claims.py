"""Tiny stand-in for the insurer's claims portal from the lesson."""


def calculate_payout(claim_amount: float, deductible: float, coverage_limit: float) -> float:
    """The insurer pays the claim minus the deductible, capped at the coverage limit, never below zero."""
    if claim_amount < 0:
        raise ValueError("claim_amount cannot be negative")
    payout = claim_amount - deductible
    return max(0.0, min(payout, coverage_limit))
