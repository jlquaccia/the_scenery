"""REST contract: status codes and response shape the Angular client (M2) depends on."""

from fastapi.testclient import TestClient


def test_ranked_list_with_coordinates(api: TestClient) -> None:
    """The roadmap 1.7 done-when, as a test."""
    response = api.get("/api/scenes", params={"genre": "thrash metal", "level": "city", "limit": 5})
    assert response.status_code == 200
    scenes = response.json()
    assert len(scenes) == 5
    assert [s["score"] for s in scenes] == sorted((s["score"] for s in scenes), reverse=True)
    for scene in scenes:
        assert scene["lat"] is not None and scene["lng"] is not None
        assert scene["level"] == "city"
        assert scene["genre"] == "thrash metal"


def test_loose_genre_names_resolve(api: TestClient) -> None:
    response = api.get("/api/scenes", params={"genre": "thrash", "level": "metro"})
    assert response.status_code == 200
    assert response.json()[0]["location"] == "San Francisco Bay Area"


def test_unknown_genre_is_404(api: TestClient) -> None:
    response = api.get("/api/scenes", params={"genre": "polka"})
    assert response.status_code == 404
    assert "polka" in response.json()["detail"]


def test_missing_genre_is_422(api: TestClient) -> None:
    assert api.get("/api/scenes").status_code == 422


def test_bad_level_is_422(api: TestClient) -> None:
    response = api.get("/api/scenes", params={"genre": "thrash", "level": "planet"})
    assert response.status_code == 422


def test_out_of_range_limit_is_422(api: TestClient) -> None:
    response = api.get("/api/scenes", params={"genre": "thrash", "limit": 500})
    assert response.status_code == 422


def test_scene_detail(api: TestClient) -> None:
    listed = api.get("/api/scenes", params={"genre": "thrash", "level": "metro", "limit": 1}).json()
    response = api.get(f"/api/scenes/{listed[0]['scene_id']}")
    assert response.status_code == 200
    detail = response.json()
    assert detail["location_path"][0] == "United States"
    assert detail["signals"]
    assert detail["signal_count"] >= len(detail["signals"])


def test_unknown_scene_is_404(api: TestClient) -> None:
    assert api.get("/api/scenes/999999").status_code == 404


def test_genre_taxonomy(api: TestClient) -> None:
    response = api.get("/api/genres")
    assert response.status_code == 200
    genres = {g["name"]: g for g in response.json()}
    assert genres["thrash metal"]["parent_name"] == "metal"
    assert genres["rock"]["parent_id"] is None
