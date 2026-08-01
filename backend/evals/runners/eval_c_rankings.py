"""Eval C — golden rankings (roadmap 1.9, DESIGN.md §10.1 C).

Measures the *data layer*: no LLM, no agent, just `scene_service.query_scenes` against
the golden cases in `evals/datasets/golden_rankings.json`. This is the eval that tests
the scoring methodology, so it is the one to iterate on when weights change (DECISIONS.md
D1's revisit trigger).

Metrics per case:
  Recall@k  — share of the case's relevant locations that land in the top k.
  NDCG@k    — graded ranking quality: rewards putting the higher-gain scenes higher.

Positions use **competition ranking**: locations with equal scores share a rank, so a
tie at the k boundary passes. The tie-break inside a score is alphabetical and carries
no meaning, and an eval that fails on it would be measuring name order.

Cases marked `known_gap` are expected to fail. They are reported and scored but never
gate the exit code — they document real gaps with their fixes. A gap that starts
passing is called out loudly so the dataset gets updated.

Run from backend/:
    .venv/bin/python -m evals.runners.eval_c_rankings          # uses .env for the DSN
    .venv/bin/python -m evals.runners.eval_c_rankings --json out.json
"""

import argparse
import json
import math
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from app.db import get_sessionmaker
from app.models.schemas import GeoLevel
from app.services import scene_service

DATASET = Path(__file__).resolve().parents[1] / "datasets" / "golden_rankings.json"
# Enough depth that a case with k=5 still sees what it narrowly missed.
FETCH_LIMIT = 20


@dataclass
class CaseResult:
    case_id: str
    genre: str
    level: str
    k: int
    recall: float
    ndcg: float
    passed: bool
    known_gap: str | None
    ranked: list[tuple[str, float, int]] = field(default_factory=list)
    problems: list[str] = field(default_factory=list)

    @property
    def status(self) -> str:
        if self.known_gap:
            return "XPASS" if self.passed else "gap"
        return "pass" if self.passed else "FAIL"


def competition_ranks(scored: list[tuple[str, float]]) -> dict[str, int]:
    """Rank by returned position, consecutive equal scores sharing a rank.

    100, 90, 90, 80 → 1, 2, 2, 4. Ranks come from the order the service actually
    returned, not from re-sorting the scores here — otherwise a broken ORDER BY
    would still score a perfect recall.
    """
    ranks: dict[str, int] = {}
    rank_of_current_score = 0
    previous_score: float | None = None
    for position, (location, score) in enumerate(scored, start=1):
        if score != previous_score:
            rank_of_current_score = position
            previous_score = score
        ranks[location] = rank_of_current_score
    return ranks


def ndcg_at_k(order: list[str], gains: dict[str, float], k: int) -> float:
    """Standard NDCG over the returned order, graded by the golden gains."""
    dcg = sum(gains.get(loc, 0.0) / math.log2(i + 2) for i, loc in enumerate(order[:k]))
    ideal = sorted(gains.values(), reverse=True)[:k]
    idcg = sum(gain / math.log2(i + 2) for i, gain in enumerate(ideal))
    return dcg / idcg if idcg else 0.0


def run_case(session: Session, case: dict[str, Any]) -> CaseResult:
    genre = scene_service.resolve_genre(session, case["genre"])
    k = int(case["k"])
    relevant: dict[str, float] = {loc: float(g) for loc, g in case["relevant"].items()}
    problems: list[str] = []

    if genre is None:
        return CaseResult(
            case_id=case["id"],
            genre=case["genre"],
            level=case["level"],
            k=k,
            recall=0.0,
            ndcg=0.0,
            passed=False,
            known_gap=case.get("known_gap"),
            problems=[f"genre {case['genre']!r} does not resolve"],
        )

    level: GeoLevel = case["level"]
    results = scene_service.query_scenes(session, genre=genre, level=level, limit=FETCH_LIMIT)
    scored = [(r.location, r.score) for r in results]
    ranks = competition_ranks(scored)

    found = {loc for loc in relevant if ranks.get(loc, sys.maxsize) <= k}
    recall = len(found) / len(relevant) if relevant else 0.0
    ndcg = ndcg_at_k([loc for loc, _ in scored], relevant, k)

    for loc in relevant:
        if loc not in found:
            where = f"rank {ranks[loc]}" if loc in ranks else "not returned"
            problems.append(f"{loc!r} missing from top {k} ({where})")

    first = case.get("must_rank_first")
    if first and ranks.get(first) != 1:
        where = f"rank {ranks[first]}" if first in ranks else "not returned"
        leader = scored[0][0] if scored else "nothing"
        problems.append(f"{first!r} should rank first but is {where}; {leader!r} leads")

    return CaseResult(
        case_id=case["id"],
        genre=genre.name,
        level=case["level"],
        k=k,
        recall=recall,
        ndcg=ndcg,
        passed=not problems,
        known_gap=case.get("known_gap"),
        ranked=[(loc, score, ranks[loc]) for loc, score in scored[:5]],
        problems=problems,
    )


def report(results: list[CaseResult], verbose: bool) -> None:
    print(f"\nEval C — golden rankings · {len(results)} cases\n")
    print(f"{'status':>6}  {'case':<28} {'recall@k':>9} {'ndcg@k':>7}")
    print("-" * 56)
    for result in results:
        print(f"{result.status:>6}  {result.case_id:<28} {result.recall:>9.2f} {result.ndcg:>7.2f}")
        for problem in result.problems:
            print(f"          ↳ {problem}")
        if verbose and result.ranked:
            top = ", ".join(f"{loc} ({score:g}, #{rank})" for loc, score, rank in result.ranked)
            print(f"          top: {top}")

    gating = [r for r in results if not r.known_gap]
    gaps = [r for r in results if r.known_gap]
    failed = [r for r in gating if not r.passed]
    mean_recall = sum(r.recall for r in gating) / len(gating) if gating else 0.0
    mean_ndcg = sum(r.ndcg for r in gating) / len(gating) if gating else 0.0

    print("-" * 56)
    print(
        f"gating: {len(gating) - len(failed)}/{len(gating)} passed · "
        f"mean recall@k {mean_recall:.2f} · mean NDCG@k {mean_ndcg:.2f}"
    )
    if gaps:
        print(f"known gaps: {len(gaps)} (reported, not gating)")
        for gap in gaps:
            print(f"  · {gap.case_id}: {gap.known_gap}")
    for gap in gaps:
        if gap.passed:
            print(
                f"\n  NOTE: known gap {gap.case_id!r} now PASSES — "
                "fix the data and promote it to a gating case, or drop it."
            )


def main() -> int:
    parser = argparse.ArgumentParser(description="Eval C — golden ranking quality")
    parser.add_argument("--dataset", type=Path, default=DATASET)
    parser.add_argument("--json", type=Path, help="write machine-readable results here")
    parser.add_argument("-v", "--verbose", action="store_true", help="show the top 5 per case")
    args = parser.parse_args()

    dataset = json.loads(args.dataset.read_text())
    with get_sessionmaker()() as session:
        results = [run_case(session, case) for case in dataset["cases"]]

    report(results, verbose=args.verbose)

    if args.json:
        args.json.write_text(
            json.dumps(
                {
                    "dataset_version": dataset["version"],
                    "cases": [
                        {
                            "id": r.case_id,
                            "status": r.status,
                            "recall_at_k": round(r.recall, 4),
                            "ndcg_at_k": round(r.ndcg, 4),
                            "problems": r.problems,
                        }
                        for r in results
                    ],
                },
                indent=2,
            )
            + "\n"
        )

    failed = [r for r in results if not r.known_gap and not r.passed]
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
