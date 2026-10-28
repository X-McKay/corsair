"""Gym exact probabilities: the binomial majority probability and Fisher's exact test.

Every expected value below is computed by hand from the formula it tests and written out
as a fraction.
"""

import pytest

from corsair.evaluation.gym.exact import fisher_exact, majority_pass_probability

# Majority pass (more than half verified) of a run of n at pooled rate p:
# sum over k > n/2 of C(n, k) p^k (1 - p)^(n - k).


@pytest.mark.parametrize(
    ("verified", "episodes", "repeats", "expected"),
    [
        # p = 1/3, n = 3: 3 (1/3)^2 (2/3) + (1/3)^3 = 6/27 + 1/27 = 7/27 (about 0.259): a
        # case verifying one episode in three passes a 3-repeat majority about 26 % of runs.
        (3, 9, 3, 7 / 27),
        # p = 1/9: 3 (1/81)(8/9) + 1/729 = 24/729 + 1/729 = 25/729 (about 0.034).
        (1, 9, 3, 25 / 729),
        # p = 2/9: 3 (4/81)(7/9) + 8/729 = 84/729 + 8/729 = 92/729 (about 0.126).
        (2, 9, 3, 92 / 729),
        # p = 8/9: 3 (64/81)(1/9) + 512/729 = 192/729 + 512/729 = 704/729.
        (8, 9, 3, 704 / 729),
        # p = 2/3: 3 (4/9)(1/3) + 8/27 = 12/27 + 8/27 = 20/27.
        (4, 6, 3, 20 / 27),
        # p = 5/6: 3 (25/36)(1/6) + 125/216 = 75/216 + 125/216 = 200/216.
        (5, 6, 3, 200 / 216),
        # An even run needs three of four: p = 1/2, C(4,3)/16 + 1/16 = 5/16.
        (4, 8, 4, 5 / 16),
        (0, 9, 3, 0.0),
        (9, 9, 3, 1.0),
    ],
)
def test_the_majority_pass_probability_is_the_binomial_tail_above_half(
    verified, episodes, repeats, expected
):
    assert majority_pass_probability(verified, episodes, repeats) == pytest.approx(expected)


def test_the_majority_pass_probability_refuses_impossible_counts():
    for verified, episodes, repeats in ((4, 3, 3), (-1, 3, 3), (0, 0, 3), (1, 3, 0)):
        with pytest.raises(ValueError, match="pooled rate"):
            majority_pass_probability(verified, episodes, repeats)


# Fisher's exact test, two-sided: with n1 first-side and n2 second-side episodes and k
# verified in all, P(x) = C(n1, x) C(n2, k - x) / C(n1 + n2, k); the p-value sums P(x) over
# every x no more probable than the observed one.


@pytest.mark.parametrize(
    ("first", "second", "expected"),
    [
        # 3/3 against 3/9: n1 3, n2 9, k 6, C(12,6) = 924; P(0..3) = 84, 378, 378, 84 / 924;
        # P(3) = 84 / 924, so p = (84 + 84) / 924 = 2/11 (about 0.182).
        ((3, 3), (3, 9), 2 / 11),
        # 3/3 against 2/9: k 5, C(12,5) = 792; P(0..3) = 126, 378, 252, 36 / 792; only P(3)
        # is at most 36, so p = 36/792 = 1/22 (about 0.045).
        ((3, 3), (2, 9), 1 / 22),
        # 2/3 against 3/9: k 5; P(2) = 252 / 792; P(0), P(2), P(3) = 126, 252, 36 are at
        # most it, so p = 414/792 (about 0.523).
        ((2, 3), (3, 9), 414 / 792),
        # 0/3 against 9/9: k 9, C(12,9) = 220; P(0..3) = 1, 27, 108, 84 / 220; p = 1/220.
        ((0, 3), (9, 9), 1 / 220),
        # 5/5 against 0/9: k 5, C(14,5) = 2002; P(0..5) = 126, 630, 840, 360, 45, 1 / 2002;
        # p = 1/2002.
        ((5, 5), (0, 9), 1 / 2002),
        # 0/5 against 4/6: k 4, C(11,4) = 330; P(0..4) = 15, 100, 150, 60, 5 / 330;
        # p = (15 + 5) / 330 = 2/33 (about 0.061).
        ((0, 5), (4, 6), 20 / 330),
        # 0/5 against 6/6: k 6, C(11,6) = 462; P(0..5) = 1, 30, 150, 200, 75, 6 / 462;
        # p = 1/462.
        ((0, 5), (6, 6), 1 / 462),
        # 2/3 against 6/9, the same rate: P(2) = 252 / 495 is the largest term, so p = 1.
        ((2, 3), (6, 9), 1.0),
    ],
)
def test_fishers_exact_test_sums_the_tables_no_more_probable_than_the_observed(
    first, second, expected
):
    assert fisher_exact(*first, *second) == pytest.approx(expected)
    # Two-sided: the test does not depend on which side is first.
    assert fisher_exact(*second, *first) == pytest.approx(expected)


def test_fishers_exact_test_refuses_impossible_counts():
    for counts in ((4, 3, 1, 3), (0, 0, 1, 3), (1, 3, -1, 3)):
        with pytest.raises(ValueError, match="verified <= episodes"):
            fisher_exact(*counts)
