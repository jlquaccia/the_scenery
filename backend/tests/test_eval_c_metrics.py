"""The metric code inside eval C.

Eval C measures the data; these test the measuring instrument. Pure functions, no
database — if the ranking or NDCG maths is wrong, every eval number is wrong with it.
"""

import pytest

from evals.runners.eval_c_rankings import competition_ranks, ndcg_at_k


def test_ranks_follow_the_returned_order() -> None:
    ranks = competition_ranks([("a", 100.0), ("b", 90.0), ("c", 50.0)])
    assert ranks == {"a": 1, "b": 2, "c": 3}


def test_equal_scores_share_a_rank_and_skip_the_next() -> None:
    """Competition ranking: 100, 90, 90, 80 → 1, 2, 2, 4."""
    ranks = competition_ranks([("a", 100.0), ("b", 90.0), ("c", 90.0), ("d", 80.0)])
    assert ranks == {"a": 1, "b": 2, "c": 2, "d": 4}


def test_a_tie_at_the_boundary_is_inside_top_k() -> None:
    """The real Gothenburg/Stockholm case: both must count as top-3."""
    ranks = competition_ranks(
        [("Helsinki", 100.0), ("Gothenburg", 83.33), ("Stockholm", 83.33), ("Chicago", 50.0)]
    )
    assert ranks["Gothenburg"] <= 3
    assert ranks["Stockholm"] <= 3
    assert ranks["Chicago"] > 3


def test_ranks_degrade_when_the_order_is_wrong() -> None:
    """Ranks come from position, so a broken ORDER BY can't score well."""
    ranks = competition_ranks([("c", 50.0), ("b", 90.0), ("a", 100.0)])
    assert ranks["a"] == 3


def test_perfect_order_scores_one() -> None:
    gains = {"a": 3.0, "b": 2.0}
    assert ndcg_at_k(["a", "b", "c"], gains, 3) == pytest.approx(1.0)


def test_inverted_order_scores_below_one() -> None:
    gains = {"a": 3.0, "b": 2.0}
    assert ndcg_at_k(["b", "a"], gains, 3) < 1.0


def test_missing_relevant_items_score_zero() -> None:
    assert ndcg_at_k(["x", "y"], {"a": 3.0}, 3) == 0.0


def test_no_relevant_items_is_zero_not_a_crash() -> None:
    assert ndcg_at_k(["a"], {}, 3) == 0.0
