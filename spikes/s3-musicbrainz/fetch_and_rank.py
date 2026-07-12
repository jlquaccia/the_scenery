"""Spike S3: can MusicBrainz data support a credible thrash city ranking?

Fetches artists tagged with a genre, groups them by begin-area (city), and
ranks cities by band count — scoring formula v1's simplest possible core
(every band = one signal of weight 1.0).

A metro-level rollup is also reported. The metro city lists below are a
stand-in for the locations-table hierarchy (city -> metro/region) that the
real schema encodes — geography definition, NOT score tuning. MusicBrainz
areas only chain city -> state/country, so metro grouping must come from our
own locations data.

Usage: python3 fetch_and_rank.py "thrash metal" [pages]
Rate limit: 1 req/sec per MusicBrainz policy.
"""

import json
import sys
import time
import urllib.parse
import urllib.request
from collections import Counter, defaultdict
from pathlib import Path

USER_AGENT = "TheScenery-spike/0.1 (jlquaccia@gmail.com)"
BASE = "https://musicbrainz.org/ws/2/artist"

# Locations-hierarchy stand-in (see module docstring).
METROS = {
    "San Francisco Bay Area": {
        "San Francisco", "Oakland", "Berkeley", "Richmond", "El Cerrito",
        "San Pablo", "Concord", "Alameda", "San Jose", "Fremont", "Hayward",
        "Daly City", "Vallejo", "Walnut Creek", "Dublin", "Livermore",
    },
    "Greater Los Angeles": {
        "Los Angeles", "Huntington Park", "Long Beach", "Anaheim", "Glendale",
        "Pasadena", "Torrance", "Downey", "Whittier", "Norwalk", "Burbank",
        "Hollywood", "Van Nuys", "Orange County",
    },
    "New York metro": {
        "New York", "New York City", "Brooklyn", "Queens", "Bronx",
        "Staten Island", "Manhattan", "Yonkers", "Newark", "Jersey City",
    },
    "Ruhr region": {
        "Essen", "Bochum", "Dortmund", "Duisburg", "Gelsenkirchen",
        "Oberhausen", "Recklinghausen", "Herne", "Katernberg",
    },
    "Greater São Paulo": {"São Paulo", "Guarulhos", "Osasco", "Santo André"},
}
CITY_TO_METRO = {c: m for m, cities in METROS.items() for c in cities}


def fetch_page(genre: str, offset: int) -> dict:
    query = urllib.parse.urlencode(
        {"query": f'tag:"{genre}"', "limit": 100, "offset": offset, "fmt": "json"}
    )
    req = urllib.request.Request(f"{BASE}?{query}", headers={"User-Agent": USER_AGENT})
    for attempt in range(4):
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                return json.load(resp)
        except urllib.error.HTTPError as e:
            if e.code in (429, 503):
                wait = 3 * (attempt + 1)
                print(f"  rate-limited ({e.code}), retrying in {wait}s", file=sys.stderr)
                time.sleep(wait)
            else:
                raise
    raise RuntimeError("giving up after retries")


def main() -> None:
    genre = sys.argv[1] if len(sys.argv) > 1 else "thrash metal"
    pages = int(sys.argv[2]) if len(sys.argv) > 2 else 5

    artists = []
    for page in range(pages):
        data = fetch_page(genre, page * 100)
        batch = data.get("artists", [])
        total = data.get("count", 0)
        artists.extend(batch)
        print(f"page {page + 1}: +{len(batch)} artists (of {total} total)", file=sys.stderr)
        if (page + 1) * 100 >= total or not batch:
            break
        time.sleep(1.1)

    city_bands: dict[str, list[str]] = defaultdict(list)
    no_area = 0
    for a in artists:
        if a.get("type") == "Person":
            continue  # bands only: scenes are made of groups
        area = a.get("begin-area") or a.get("area")
        if not area:
            no_area += 1
            continue
        city_bands[area["name"]].append(a["name"])

    city_counts = Counter({city: len(bands) for city, bands in city_bands.items()})

    metro_counts: Counter = Counter()
    metro_bands: dict[str, list[str]] = defaultdict(list)
    for city, bands in city_bands.items():
        metro = CITY_TO_METRO.get(city, city)
        metro_counts[metro] += len(bands)
        metro_bands[metro].extend(bands)

    print(f"\n=== {genre} — {len(artists)} artists fetched, "
          f"{sum(city_counts.values())} bands with a location, {no_area} without ===")
    print("\nTop 15 cities (raw begin-area):")
    for city, n in city_counts.most_common(15):
        print(f"  {n:4d}  {city}")
    print("\nTop 15 after metro rollup:")
    for metro, n in metro_counts.most_common(15):
        sample = ", ".join(sorted(metro_bands[metro], key=str.lower)[:4])
        print(f"  {n:4d}  {metro}   e.g. {sample}")

    out = Path(__file__).parent / "results" / f"{genre.replace(' ', '_')}.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(
        {
            "genre": genre,
            "artists_fetched": len(artists),
            "cities": {c: sorted(b) for c, b in sorted(city_bands.items())},
            "city_ranking": city_counts.most_common(),
            "metro_ranking": metro_counts.most_common(),
        },
        indent=2, ensure_ascii=False,
    ))
    print(f"\nsaved -> {out}")


if __name__ == "__main__":
    main()
