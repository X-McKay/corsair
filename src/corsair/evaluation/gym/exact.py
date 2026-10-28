"""Exact small-count probabilities the noise band and the gate read; pure arithmetic.

Counts are a few episodes per case (three repeats in two or three runs), so both
probabilities are computed exactly with rationals and returned as floats:

- ``majority_pass_probability``: with a case's pooled episode rate p = verified /
  episodes, the binomial probability that one run of ``repeats`` episodes gets a
  majority pass (``scoring.is_majority``, more than half verified).
- ``fisher_exact``: Fisher's exact test, two-sided, on a 2x2 table of verified and
  unverified episodes on two sides; the p-value sums the hypergeometric probabilities of
  every table with the observed margins that is no more probable than the observed one.
"""

from fractions import Fraction
from math import comb

from corsair.evaluation.gym.scoring import is_majority


def majority_pass_probability(verified: int, episodes: int, repeats: int) -> float:
    """P(a run of ``repeats`` episodes at rate verified / episodes passes by majority)."""
    if episodes < 1 or not 0 <= verified <= episodes or repeats < 1:
        raise ValueError("a pooled rate needs 0 <= verified <= episodes, episodes and repeats >= 1")
    rate = Fraction(verified, episodes)
    return float(
        sum(
            comb(repeats, count) * rate**count * (1 - rate) ** (repeats - count)
            for count in range(repeats + 1)
            if is_majority(count, repeats)
        )
    )


def fisher_exact(
    first_verified: int, first_episodes: int, second_verified: int, second_episodes: int
) -> float:
    """Two-sided Fisher's exact p-value of first's verified rate against second's.

    The table is [[first verified, first unverified], [second verified, second
    unverified]]. With row totals n1, n2 and k verified in all, P(x) = C(n1, x) C(n2, k - x)
    / C(n1 + n2, k) for x first-side verified; the p-value is the sum of P(x) over every x
    with P(x) <= P(observed), compared exactly.
    """
    for verified, episodes in (
        (first_verified, first_episodes),
        (second_verified, second_episodes),
    ):
        if episodes < 1 or not 0 <= verified <= episodes:
            raise ValueError("each side needs 0 <= verified <= episodes and one episode")
    total = first_episodes + second_episodes
    successes = first_verified + second_verified
    tables = comb(total, successes)
    low, high = max(0, successes - second_episodes), min(first_episodes, successes)
    probability = {
        x: Fraction(comb(first_episodes, x) * comb(second_episodes, successes - x), tables)
        for x in range(low, high + 1)
    }
    observed = probability[first_verified]
    return float(sum(value for value in probability.values() if value <= observed))
