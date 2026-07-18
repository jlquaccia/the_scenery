"""The Scenery — FastAPI application entry point."""

from fastapi import FastAPI

app = FastAPI(title="The Scenery API")


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "service": "the-scenery-api"}
