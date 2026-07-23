"""Generate the context:seed changeset from MusicBrainz + Wikidata.

Method per spike S3 (spikes/NOTES.md) and DECISIONS.md D1:
  * artists by genre tag (bands only, identity = MBID, located via begin-area)
  * area parent chains resolved via /ws/2/area/{id} (cached in .cache/)
  * metro regions are OUR curated rows (MusicBrainz has none)
  * coordinates batched from Wikidata (MB areas carry none)
  * cities need >= MIN_BANDS bands for a genre to seed a scene (noise filter)

Output: backend/db/changelog/changesets/005-seed-data.sql (deterministic,
reviewable, applied only under Liquibase context `seed`). Scene scores stay 0 —
the scoring job (roadmap 1.6) computes them.

Run from backend/:  .venv/bin/python -m ingestion.generate_seed
"""

import json
import re
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

USER_AGENT = "TheScenery-seed/0.1 (jlquaccia@gmail.com)"
MB = "https://musicbrainz.org/ws/2"
WIKIDATA = "https://www.wikidata.org/w/api.php"
CACHE = Path(__file__).parent / ".cache" / "areas.json"
OUT = Path(__file__).parent.parent / "db" / "changelog" / "changesets" / "005-seed-data.sql"

PAGES_PER_GENRE = 2  # x100 artists, search-relevance order
MIN_BANDS = 2  # a city seeds a scene only with >= this many bands

# Genre taxonomy: (name, parent name or None, mb tag or None). Tagged = scene genre.
GENRES: list[tuple[str, str | None, str | None]] = [
    ("rock", None, None),
    ("metal", "rock", None),
    ("thrash metal", "metal", "thrash metal"),
    ("death metal", "metal", None),
    ("melodic death metal", "death metal", "melodic death metal"),
    ("grunge", "rock", "grunge"),
    ("electronic", None, None),
    ("techno", "electronic", "techno"),
    ("hip hop", None, "hip hop"),
]

# Curated metro rows (S3 finding 3: geography curation, not score tuning).
METROS: dict[str, dict[str, Any]] = {
    "San Francisco Bay Area": {
        "state": "California",
        "coords": (37.8272, -122.2913),
        "cities": {
            "San Francisco",
            "Oakland",
            "Berkeley",
            "Richmond",
            "El Cerrito",
            "San Pablo",
            "Concord",
            "Alameda",
            "San Jose",
            "Fremont",
            "Hayward",
            "Daly City",
            "Vallejo",
            "Walnut Creek",
            "Dublin",
            "Livermore",
        },
    },
    "Greater Los Angeles": {
        "state": "California",
        "coords": (34.0201, -118.4119),
        "cities": {
            "Los Angeles",
            "Huntington Park",
            "Long Beach",
            "Anaheim",
            "Glendale",
            "Pasadena",
            "Torrance",
            "Downey",
            "Whittier",
            "Norwalk",
            "Burbank",
            "Hollywood",
            "Van Nuys",
            "Compton",
            "Inglewood",
        },
    },
    "New York metro": {
        "state": "New York",
        "coords": (40.7128, -74.006),
        "cities": {
            "New York",
            "New York City",
            "Brooklyn",
            "Queens",
            "The Bronx",
            "Staten Island",
            "Manhattan",
            "Yonkers",
            "Newark",
            "Jersey City",
        },
    },
    "Ruhr region": {
        "state": "North Rhine-Westphalia",
        "coords": (51.5, 7.25),
        "cities": {
            "Essen",
            "Bochum",
            "Dortmund",
            "Duisburg",
            "Gelsenkirchen",
            "Oberhausen",
            "Recklinghausen",
            "Herne",
            "Katernberg",
        },
    },
    "Greater São Paulo": {
        "state": "São Paulo",
        "coords": (-23.55, -46.63),
        "cities": {"São Paulo", "Guarulhos", "Osasco", "Santo André"},
    },
}

CITY_TYPES = {"City", "Town", "Village", "Municipality"}
STATE_TYPES = {"Subdivision"}


def http_json(url: str) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    for attempt in range(5):
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                return json.load(resp)
        except urllib.error.HTTPError as e:
            if e.code in (429, 503):
                time.sleep(3 * (attempt + 1))
            else:
                raise
    raise RuntimeError(f"giving up on {url}")


def mb_get(path: str, **params: str) -> dict:
    time.sleep(1.1)  # MusicBrainz rate limit
    q = urllib.parse.urlencode({**params, "fmt": "json"})
    return http_json(f"{MB}/{path}?{q}")


class AreaResolver:
    """Resolve MB area ids to (name, type, parent chain, wikidata QID), cached."""

    def __init__(self) -> None:
        self.cache: dict[str, dict] = {}
        if CACHE.exists():
            self.cache = json.loads(CACHE.read_text())

    def save(self) -> None:
        CACHE.parent.mkdir(exist_ok=True)
        CACHE.write_text(json.dumps(self.cache, indent=1, sort_keys=True))

    def get(self, area_id: str) -> dict:
        if area_id in self.cache:
            return self.cache[area_id]
        data = mb_get(f"area/{area_id}", inc="area-rels+url-rels")
        parent = None
        wikidata = None
        for rel in data.get("relations", []):
            if rel.get("type") == "part of" and rel.get("direction") == "backward":
                a = rel.get("area") or {}
                parent = {"id": a.get("id"), "name": a.get("name"), "type": a.get("type")}
            if rel.get("type") == "wikidata":
                url = rel.get("url", {}).get("resource", "")
                m = re.search(r"(Q\d+)$", url)
                wikidata = m.group(1) if m else None
        entry = {
            "name": data.get("name"),
            "type": data.get("type"),
            "parent": parent,
            "wikidata": wikidata,
        }
        self.cache[area_id] = entry
        self.save()
        return entry

    def chain(self, area_id: str) -> list[dict]:
        """Area + ancestors, bottom-up, each {id, name, type, wikidata}."""
        out: list[dict] = []
        cur: str | None = area_id
        seen: set[str] = set()
        while cur and cur not in seen:
            seen.add(cur)
            e = self.get(cur)
            out.append({"id": cur, **e})
            cur = (e.get("parent") or {}).get("id")
        return out


def wikidata_coords(qids: list[str]) -> dict[str, tuple[float, float]]:
    coords: dict[str, tuple[float, float]] = {}
    for i in range(0, len(qids), 50):
        batch = qids[i : i + 50]
        q = urllib.parse.urlencode(
            {"action": "wbgetentities", "ids": "|".join(batch), "props": "claims", "format": "json"}
        )
        data = http_json(f"{WIKIDATA}?{q}")
        for qid, ent in data.get("entities", {}).items():
            claims = ent.get("claims", {}).get("P625", [])
            if claims:
                v = claims[0].get("mainsnak", {}).get("datavalue", {}).get("value", {})
                if "latitude" in v:
                    coords[qid] = (round(v["latitude"], 6), round(v["longitude"], 6))
        time.sleep(0.5)
    return coords


def sql_str(s: str | None) -> str:
    if s is None:
        return "NULL"
    return "'" + s.replace("\\", "\\\\").replace("'", "''") + "'"


def main() -> int:
    resolver = AreaResolver()
    scene_genres = [(name, tag) for name, _, tag in GENRES if tag]

    # 1. Fetch bands per genre --------------------------------------------------
    bands_by_genre: dict[str, list[dict]] = {}
    for name, tag in scene_genres:
        artists: list[dict] = []
        for page in range(PAGES_PER_GENRE):
            data = mb_get("artist", query=f'tag:"{tag}"', limit="100", offset=str(page * 100))
            artists.extend(data.get("artists", []))
        # Dedupe by MBID — search pagination can return the same artist twice.
        bands: dict[str, dict] = {}
        for a in artists:
            if a.get("type") == "Group" and (a.get("begin-area") or a.get("area")):
                bands.setdefault(a["id"], a)
        bands_by_genre[name] = list(bands.values())
        print(f"{name}: {len(bands)} located bands", file=sys.stderr)

    # 2. Resolve every referenced area chain -----------------------------------
    area_ids = {
        (b.get("begin-area") or b.get("area"))["id"]
        for bands in bands_by_genre.values()
        for b in bands
    }
    print(f"resolving {len(area_ids)} unique areas…", file=sys.stderr)
    chains: dict[str, list[dict]] = {aid: resolver.chain(aid) for aid in area_ids}

    def classify(chain: list[dict]) -> dict[str, dict | None]:
        """Pick the city / state / country nodes out of a bottom-up chain."""
        city = state = country = None
        for node in chain:
            t = node.get("type")
            if t in CITY_TYPES and city is None:
                city = node
            elif t in STATE_TYPES and state is None:
                state = node
            elif t == "Country" and country is None:
                country = node
        return {"city": city, "state": state, "country": country}

    # 3. Count bands per (genre, city). Keep cities with >= MIN_BANDS — except
    # metro-member cities, which are kept at any count: scenes like the Bay Area
    # are SPREAD across many small cities, and dropping one-band towns would
    # gut exactly the rollup the metro tier exists for.
    metro_city_names = {c for m in METROS.values() for c in m["cities"]}
    city_bands: dict[tuple[str, str], list[dict]] = {}
    city_names: dict[str, str] = {}
    for genre, bands in bands_by_genre.items():
        for b in bands:
            aid = (b.get("begin-area") or b.get("area"))["id"]
            c = classify(chains[aid])
            if c["city"]:
                city_bands.setdefault((genre, c["city"]["id"]), []).append(b)
                city_names[c["city"]["id"]] = c["city"]["name"]
    kept = {
        k: v
        for k, v in city_bands.items()
        if len(v) >= MIN_BANDS or city_names[k[1]] in metro_city_names
    }
    kept_city_ids = {cid for (_, cid) in kept}

    # 4. Build location rows: countries, states, metros, cities ----------------
    loc_ids: dict[str, int] = {}  # key -> assigned id
    rows: list[dict] = []

    def add_loc(
        key: str,
        name: str,
        level: str,
        parent_key: str | None,
        coords: tuple[float, float] | None,
        mbid: str | None,
    ) -> int:
        if key in loc_ids:
            return loc_ids[key]
        loc_ids[key] = len(rows) + 1
        rows.append(
            {
                "id": loc_ids[key],
                "name": name,
                "level": level,
                "parent_key": parent_key,
                "coords": coords,
                "mbid": mbid,
            }
        )
        return loc_ids[key]

    needed: dict[str, dict] = {}
    for cid in sorted(kept_city_ids):
        c = classify(chains[cid])
        for role in ("country", "state", "city"):
            node = c[role]
            if node:
                needed.setdefault(node["id"], {**node, "role": role})

    qids = sorted({n["wikidata"] for n in needed.values() if n.get("wikidata")})
    print(f"fetching coordinates for {len(qids)} areas from Wikidata…", file=sys.stderr)
    coords_by_qid = wikidata_coords(qids)

    def node_coords(node: dict) -> tuple[float, float] | None:
        return coords_by_qid.get(node.get("wikidata") or "")

    city_metro = {city: metro for metro, m in METROS.items() for city in m["cities"]}

    for node in sorted(needed.values(), key=lambda n: n["name"]):
        if node["role"] == "country":
            add_loc(node["id"], node["name"], "country", None, node_coords(node), node["id"])
    for node in sorted(needed.values(), key=lambda n: n["name"]):
        if node["role"] == "state":
            c = None
            for cid in kept_city_ids:
                cl = classify(chains[cid])
                if cl["state"] and cl["state"]["id"] == node["id"] and cl["country"]:
                    c = cl["country"]["id"]
                    break
            add_loc(node["id"], node["name"], "state", c, node_coords(node), node["id"])
    state_by_name = {
        rows[i - 1]["name"]: k for k, i in loc_ids.items() if rows[i - 1]["level"] == "state"
    }
    for metro, m in sorted(METROS.items()):
        add_loc(f"metro:{metro}", metro, "metro", state_by_name.get(m["state"]), m["coords"], None)
    for cid in sorted(kept_city_ids, key=lambda i: needed[i]["name"]):
        cl = classify(chains[cid])
        city = cl["city"]
        assert city is not None
        metro = city_metro.get(city["name"])
        parent = (
            f"metro:{metro}"
            if metro
            else (cl["state"] or {}).get("id") or (cl["country"] or {}).get("id")
        )
        add_loc(cid, city["name"], "city", parent, node_coords(city), cid)

    # 5. Scenes + signals -------------------------------------------------------
    genre_ids = {name: i + 1 for i, (name, _, _) in enumerate(GENRES)}
    scenes: list[dict] = []
    signals: list[dict] = []
    for (genre, cid), bands in sorted(kept.items()):
        scene_id = len(scenes) + 1
        scenes.append({"id": scene_id, "genre_id": genre_ids[genre], "location_key": cid})
        for b in sorted(bands, key=lambda x: x["name"]):
            meta = {
                k: v
                for k, v in {
                    "begin": (b.get("life-span") or {}).get("begin"),
                    "ended": (b.get("life-span") or {}).get("ended"),
                    "disambiguation": b.get("disambiguation") or None,
                }.items()
                if v is not None
            }
            signals.append(
                {
                    "scene_id": scene_id,
                    "type": "band",
                    "name": b["name"],
                    "mb_id": b["id"],
                    "meta": meta,
                }
            )

    # 6. Emit SQL ---------------------------------------------------------------
    L: list[str] = ["--liquibase formatted sql", ""]
    L.append("--changeset jason:007-seed-genres context:seed")
    L.append("--comment Generated by ingestion/generate_seed.py — do not hand-edit.")
    for i, (name, parent, _tag) in enumerate(GENRES, start=1):
        pid = genre_ids[parent] if parent else None
        L.append(
            f"INSERT INTO genres (id, name, parent_id) VALUES "
            f"({i}, {sql_str(name)}, {pid if pid else 'NULL'});"
        )
    # genres is self-referencing (parent_id) — a plain DELETE hits its own FK.
    L.append("--rollback SET FOREIGN_KEY_CHECKS=0;")
    L.append("--rollback DELETE FROM genres;")
    L.append("--rollback SET FOREIGN_KEY_CHECKS=1;")
    L.append("")
    L.append("--changeset jason:008-seed-locations context:seed")
    for r in rows:
        pid = loc_ids[r["parent_key"]] if r["parent_key"] else None
        lat, lng = r["coords"] if r["coords"] else (None, None)
        L.append(
            f"INSERT INTO locations (id, name, level, parent_id, lat, lng, mb_area_id) VALUES "
            f"({r['id']}, {sql_str(r['name'])}, '{r['level']}', "
            f"{pid if pid else 'NULL'}, {lat if lat is not None else 'NULL'}, "
            f"{lng if lng is not None else 'NULL'}, {sql_str(r['mbid'])});"
        )
    L.append("--rollback SET FOREIGN_KEY_CHECKS=0;")
    L.append("--rollback DELETE FROM locations;")
    L.append("--rollback SET FOREIGN_KEY_CHECKS=1;")
    L.append("")
    L.append("--changeset jason:009-seed-scenes context:seed")
    for s in scenes:
        L.append(
            f"INSERT INTO scenes (id, genre_id, location_id) VALUES "
            f"({s['id']}, {s['genre_id']}, {loc_ids[s['location_key']]});"
        )
    L.append("--rollback DELETE FROM scenes;")
    L.append("")
    L.append("--changeset jason:010-seed-signals context:seed")
    for sig in signals:
        L.append(
            f"INSERT INTO scene_signals (scene_id, signal_type, name, weight, mb_id, metadata) "
            f"VALUES ({sig['scene_id']}, 'band', {sql_str(sig['name'])}, 1.0, "
            f"{sql_str(sig['mb_id'])}, {sql_str(json.dumps(sig['meta']))});"
        )
    L.append("--rollback DELETE FROM scene_signals;")
    L.append("")

    OUT.write_text("\n".join(L))
    print(
        f"wrote {OUT.name}: {len(GENRES)} genres, {len(rows)} locations, "
        f"{len(scenes)} scenes, {len(signals)} signals"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
