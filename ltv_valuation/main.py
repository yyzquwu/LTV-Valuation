from __future__ import annotations

import os

import uvicorn
from fastapi import FastAPI, HTTPException

from .models import PropertySummaryRequest
from .property_summary import generate_property_summary
from .trestle_client import TrestleClient


def _config() -> dict:
    return {
        "base_uri": os.getenv("TRESTLE_BASE_URI", "https://api-trestle.corelogic.com/trestle/odata"),
        "token_url": os.getenv("TRESTLE_TOKEN_URL", "https://api-trestle.corelogic.com/trestle/oidc/connect/token"),
        "client_id": os.getenv("TRESTLE_CLIENT_ID", ""),
        "client_secret": os.getenv("TRESTLE_CLIENT_SECRET", ""),
        "scope": os.getenv("TRESTLE_SCOPE", "api"),
    }


app = FastAPI(title="LTV Valuation", version="0.1.0")


@app.get("/health")
def health() -> dict:
    config = _config()
    return {"ok": True, "configured": bool(config["client_id"] and config["client_secret"]), "basePath": "/api/trestle"}


@app.post("/api/trestle/properties/list")
def properties_list(payload: dict) -> list[dict]:
    try:
        client = TrestleClient(**_config())
        items = client.list_properties(
            filter=payload.get("filter"),
            select=payload.get("select"),
            orderby=payload.get("orderby"),
            top=payload.get("top", 1000),
            max_records=payload.get("maxRecords"),
        )
        return [item.model_dump() for item in items]
    except Exception as exc:  # pragma: no cover
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/api/trestle/properties/{listing_key}")
def property_by_listing_key(listing_key: str) -> dict | None:
    try:
        client = TrestleClient(**_config())
        item = client.property_by_listing_key(listing_key)
        return item.model_dump() if item else None
    except Exception as exc:  # pragma: no cover
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/api/trestle/valuation/summary")
def valuation_summary(request: PropertySummaryRequest) -> dict:
    try:
        summary = generate_property_summary(_config(), request)
        return summary.model_dump(by_alias=True)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # pragma: no cover
        raise HTTPException(status_code=500, detail=str(exc)) from exc


def run() -> None:
    uvicorn.run("ltv_valuation.main:app", host="0.0.0.0", port=int(os.getenv("PORT", "8787")))


if __name__ == "__main__":
    run()
