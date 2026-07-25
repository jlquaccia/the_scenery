"""Scoring batch job — formula v1 (DECISIONS.md D1).

scene_score(genre, location) = Σ band-signal weights across the location AND all
its descendants (city → metro/region → country rollup), normalized 0–100 per
(genre, level): 100 * raw / max_raw_for_that_genre_and_level.

Because scoring rolls signals up the hierarchy, this job also MATERIALIZES the
rollup scene rows (metro/state/country) so "biggest thrash scene at the state
level" stays a single indexed lookup (DESIGN.md §3.3). Idempotent: every scene
is reset to 0, then recomputed, so stale rollups decay correctly.

Run from backend/:
    MYSQL_DSN=mysql://scenery_app:...@localhost:3306/scenery \
        .venv/bin/python -m ingestion.compute_scores
"""

import os
import sys
from collections import defaultdict
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import create_engine, func, select, update
from sqlalchemy.orm import Session

from app.models import Location, Scene, SceneSignal


def compute() -> int:
    dsn = os.environ.get("MYSQL_DSN", "")
    if not dsn:
        print("MYSQL_DSN is required (needs INSERT/UPDATE — e.g. the app user)")
        return 2
    engine = create_engine(dsn.replace("mysql://", "mysql+pymysql://", 1))

    with Session(engine) as session:
        # 1. Location tree: id -> parent_id, id -> level.
        parents: dict[int, int | None] = {}
        levels: dict[int, str] = {}
        for loc_id, parent_id, level in session.execute(
            select(Location.id, Location.parent_id, Location.level)
        ):
            parents[loc_id] = parent_id
            levels[loc_id] = level

        # 2. Direct band weight per (genre, city) from signals.
        base: dict[tuple[int, int], Decimal] = defaultdict(Decimal)
        for genre_id, loc_id, total in session.execute(
            select(
                Scene.genre_id,
                Scene.location_id,
                func.coalesce(func.sum(SceneSignal.weight), 0),
            )
            .join(SceneSignal, SceneSignal.scene_id == Scene.id)
            .group_by(Scene.genre_id, Scene.location_id)
        ):
            base[(genre_id, loc_id)] += Decimal(total)

        # 3. Roll each city's weight up into every ancestor location.
        rolled: dict[tuple[int, int], Decimal] = defaultdict(Decimal)
        for (genre_id, loc_id), raw in base.items():
            node: int | None = loc_id
            seen: set[int] = set()
            while node is not None and node not in seen:
                seen.add(node)
                rolled[(genre_id, node)] += raw
                node = parents.get(node)

        # 4. Normalize 0–100 within each (genre, level).
        max_by_level: dict[tuple[int, str], Decimal] = defaultdict(Decimal)
        for (genre_id, loc_id), raw in rolled.items():
            key = (genre_id, levels[loc_id])
            max_by_level[key] = max(max_by_level[key], raw)

        scores: dict[tuple[int, int], Decimal] = {}
        for (genre_id, loc_id), raw in rolled.items():
            mx = max_by_level[(genre_id, levels[loc_id])]
            scores[(genre_id, loc_id)] = round(Decimal(100) * raw / mx, 2) if mx else Decimal(0)

        # 5. Reset then upsert. Existing scenes update in place; rollup scenes
        # (metro/state/country) that don't exist yet get created.
        existing: dict[tuple[int, int], int] = {
            (g, loc): sid
            for sid, g, loc in session.execute(select(Scene.id, Scene.genre_id, Scene.location_id))
        }
        now = datetime.now(UTC)
        session.execute(update(Scene).values(scene_score=Decimal(0), score_updated_at=now))

        created = 0
        for (genre_id, loc_id), score in scores.items():
            if (genre_id, loc_id) in existing:
                session.execute(
                    update(Scene)
                    .where(Scene.id == existing[(genre_id, loc_id)])
                    .values(scene_score=score, score_updated_at=now)
                )
            else:
                session.add(
                    Scene(
                        genre_id=genre_id,
                        location_id=loc_id,
                        scene_score=score,
                        score_updated_at=now,
                    )
                )
                created += 1
        session.commit()

    print(
        f"scored {len(scores)} (genre, location) scenes "
        f"({created} rollup scenes created); reset {len(existing)} existing rows first"
    )
    return 0


if __name__ == "__main__":
    sys.exit(compute())
