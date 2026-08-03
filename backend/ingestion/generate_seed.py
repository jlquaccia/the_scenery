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

PAGES_PER_GENRE = 5  # x100 artists, search-relevance order
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
# `state` must be spelled the way MUSICBRAINZ spells it — it disambiguates
# same-named cities, and a mismatch would silently empty the metro (which is why
# main() asserts every metro captured at least one city).
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
    "Greater Seattle": {
        # Seattle–Tacoma–Bellevue MSA (King, Pierce, Snohomish counties). Aberdeen
        # and Olympia are deliberately out: both are grunge-adjacent but ~60–100
        # miles away and belong to their own areas, not this metro.
        "state": "Washington",
        "coords": (47.606111, -122.332778),
        "cities": {
            "Seattle",
            "Tacoma",
            "Bellevue",
            "Everett",
            "Kent",
            "Renton",
            "Kirkland",
            "Redmond",
            "Auburn",
            "Bothell",
            "Federal Way",
            "Shoreline",
            "Burien",
            "Sammamish",
            "Puyallup",
            "Lakewood",
            "Edmonds",
            "Lynnwood",
        },
    },
    "Ruhr region": {
        # MusicBrainz spells the state in German — see the note above.
        "state": "Nordrhein-Westfalen",
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
    for attempt in range(6):
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                return json.load(resp)
        except urllib.error.HTTPError as e:  # a subclass of OSError — must come first
            if e.code in (429, 503):
                time.sleep(3 * (attempt + 1))
            else:
                raise
        except OSError as e:
            # Connection reset, read timeout, DNS blip. A full run makes several
            # hundred sequential requests, so a transient failure is expected
            # rather than exceptional — retry instead of losing the whole run.
            print(f"  retrying after {type(e).__name__}: {url}", file=sys.stderr)
            time.sleep(3 * (attempt + 1))
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
        loose = 0
        solo = 0
        for a in artists:
            # D1 as amended (roadmap 1.11): Group AND Person both count. A
            # Group-only rule made techno's founders invisible — Juan Atkins,
            # Derrick May, Kevin Saunderson are all typed Person — and any genre
            # built on producers rather than bands was undercounted the same way.
            if a.get("type") not in ("Group", "Person"):
                continue
            if not (a.get("begin-area") or a.get("area")):
                continue
            # The tag search matches loosely: `tag:"techno"` returns trance acts,
            # industrial rock, and J-pop tagged "techno kayō", ranked by fame
            # rather than tag strength. Require the artist to actually carry this
            # exact tag with positive net votes, or the genre means nothing.
            if not any(t.get("name") == tag and t.get("count", 0) >= 1 for t in a.get("tags", [])):
                loose += 1
                continue
            if a.get("type") == "Person":
                solo += 1
            bands.setdefault(a["id"], a)
        bands_by_genre[name] = list(bands.values())
        print(
            f"{name}: {len(bands)} located artists ({solo} solo, "
            f"{loose} dropped as loosely tagged)",
            file=sys.stderr,
        )

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
    # Keyed by (city, state) for the same reason metro_of() is — otherwise
    # Richmond, Virginia inherits the Bay Area's exemption.
    metro_city_keys = {(c, m["state"]) for m in METROS.values() for c in m["cities"]}
    city_bands: dict[tuple[str, str], list[dict]] = {}
    city_names: dict[str, str] = {}
    city_keys: dict[str, tuple[str, str | None]] = {}
    for genre, bands in bands_by_genre.items():
        for b in bands:
            aid = (b.get("begin-area") or b.get("area"))["id"]
            c = classify(chains[aid])
            if c["city"]:
                city_bands.setdefault((genre, c["city"]["id"]), []).append(b)
                city_names[c["city"]["id"]] = c["city"]["name"]
                city_keys[c["city"]["id"]] = (
                    c["city"]["name"],
                    (c["state"] or {}).get("name"),
                )
    kept = {
        k: v
        for k, v in city_bands.items()
        if len(v) >= MIN_BANDS or city_keys[k[1]] in metro_city_keys
    }

    # 3b. Attribute EVERY artist to a location (roadmap 1.11). MIN_BANDS decides
    # whether a *city scene* exists, not whether an artist counts: an artist in a
    # sub-threshold city attaches to the nearest ancestor that does have a scene,
    # and one whose area resolves to no city at all (MusicBrainz `begin-area` is
    # often just "Germany") attaches to the state or country — spike S3 finding #2,
    # never implemented until now. Previously both cases were discarded outright,
    # losing ~40% of located artists and undercounting every rollup above them.
    attributed: dict[tuple[str, str], list[dict]] = {}
    needed: dict[str, dict] = {}
    state_country: dict[str, str] = {}  # state id -> its country id
    city_parent: dict[str, dict | None] = {}  # city id -> its state node (or None)
    dropped_no_geography = 0
    attached_above_city = 0
    for genre, bands in bands_by_genre.items():
        for b in bands:
            aid = (b.get("begin-area") or b.get("area"))["id"]
            cl = classify(chains[aid])
            if cl["state"] and cl["country"]:
                state_country.setdefault(cl["state"]["id"], cl["country"]["id"])
            if cl["city"]:
                city_parent.setdefault(cl["city"]["id"], cl["state"] or cl["country"])
            # Ancestors always get a row; a city only when it earned a scene.
            if cl["country"]:
                needed.setdefault(cl["country"]["id"], {**cl["country"], "role": "country"})
            if cl["state"]:
                needed.setdefault(cl["state"]["id"], {**cl["state"], "role": "state"})
            if cl["city"] and (genre, cl["city"]["id"]) in kept:
                needed.setdefault(cl["city"]["id"], {**cl["city"], "role": "city"})
                target = cl["city"]
            elif cl["state"]:
                target = cl["state"]
                attached_above_city += 1
            elif cl["country"]:
                target = cl["country"]
                attached_above_city += 1
            elif cl["city"]:  # a city with no resolvable ancestors — keep it anyway
                needed.setdefault(cl["city"]["id"], {**cl["city"], "role": "city"})
                target = cl["city"]
            else:
                dropped_no_geography += 1
                continue
            attributed.setdefault((genre, target["id"]), []).append(b)
    print(
        f"attributed {sum(len(v) for v in attributed.values())} artists "
        f"({attached_above_city} above city level, {dropped_no_geography} with no geography)",
        file=sys.stderr,
    )

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

    qids = sorted({n["wikidata"] for n in needed.values() if n.get("wikidata")})
    print(f"fetching coordinates for {len(qids)} areas from Wikidata…", file=sys.stderr)
    coords_by_qid = wikidata_coords(qids)

    def node_coords(node: dict) -> tuple[float, float] | None:
        return coords_by_qid.get(node.get("wikidata") or "")

    def metro_of(city_node: dict, state_node: dict | None) -> str | None:
        """Metro membership keyed by (city name, state).

        Name alone is not an identifier: 'Richmond' is both a Bay Area city and
        the capital of Virginia, and matching on name put GWAR in the Bay Area
        thrash scene (roadmap 1.10).
        """
        state_name = (state_node or {}).get("name")
        for metro, m in METROS.items():
            if city_node["name"] in m["cities"] and state_name == m["state"]:
                return metro
        return None

    for node in sorted(needed.values(), key=lambda n: n["name"]):
        if node["role"] == "country":
            add_loc(node["id"], node["name"], "country", None, node_coords(node), node["id"])
    for node in sorted(needed.values(), key=lambda n: n["name"]):
        if node["role"] == "state":
            country_key = state_country.get(node["id"])
            add_loc(node["id"], node["name"], "state", country_key, node_coords(node), node["id"])
    state_by_name = {
        rows[i - 1]["name"]: k for k, i in loc_ids.items() if rows[i - 1]["level"] == "state"
    }
    for metro, m in sorted(METROS.items()):
        add_loc(f"metro:{metro}", metro, "metro", state_by_name.get(m["state"]), m["coords"], None)
    metro_members: dict[str, list[str]] = {metro: [] for metro in METROS}
    city_nodes = [n for n in needed.values() if n["role"] == "city"]
    for city in sorted(city_nodes, key=lambda n: n["name"]):
        above = city_parent.get(city["id"])
        metro = metro_of(city, above if (above or {}).get("type") in STATE_TYPES else None)
        if metro:
            metro_members[metro].append(city["name"])
        parent = f"metro:{metro}" if metro else (above or {}).get("id")
        add_loc(city["id"], city["name"], "city", parent, node_coords(city), city["id"])

    # A metro that captured nothing means its `state` spelling no longer matches
    # MusicBrainz — the silent failure this guard exists to make loud.
    for metro, members in sorted(metro_members.items()):
        if not members:
            print(f"ERROR: metro {metro!r} captured no cities — check its 'state'", file=sys.stderr)
            return 1
        print(f"metro {metro}: {len(members)} cities", file=sys.stderr)

    # 5. Scenes + signals -------------------------------------------------------
    genre_ids = {name: i + 1 for i, (name, _, _) in enumerate(GENRES)}
    scenes: list[dict] = []
    signals: list[dict] = []
    for (genre, loc_key), bands in sorted(attributed.items()):
        scene_id = len(scenes) + 1
        scenes.append({"id": scene_id, "genre_id": genre_ids[genre], "location_key": loc_key})
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
                    # Groups are 'band', solo acts 'artist' — kept distinct so the
                    # two can be weighted separately later without a reseed.
                    "type": "band" if b.get("type") == "Group" else "artist",
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
            f"VALUES ({sig['scene_id']}, '{sig['type']}', {sql_str(sig['name'])}, 1.0, "
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
