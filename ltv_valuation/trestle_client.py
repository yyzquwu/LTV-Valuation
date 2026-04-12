from __future__ import annotations

from typing import Protocol

import httpx

from .models import Property


class MLSClient(Protocol):
    def list_properties(self, *, filter: str | None = None, select: list[str] | None = None, orderby: str | None = None, top: int = 1000, max_records: int | None = None) -> list[Property]: ...
    def property_by_listing_key(self, listing_key: str, select: list[str] | None = None) -> Property | None: ...
    def list_media_by_listing_key(self, listing_key: str) -> list[dict]: ...


class TrestleClient:
    def __init__(self, base_uri: str, token_url: str, client_id: str, client_secret: str, scope: str = "api") -> None:
        self.base_uri = base_uri.rstrip("/")
        self.token_url = token_url
        self.client_id = client_id
        self.client_secret = client_secret
        self.scope = scope
        self._access_token: str | None = None
        self._expires_at: float = 0

    def _token(self) -> str:
        import time

        if self._access_token and time.time() < self._expires_at - 60:
            return self._access_token
        response = httpx.post(
            self.token_url,
            data={
                "grant_type": "client_credentials",
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "scope": self.scope,
            },
            timeout=30,
        )
        response.raise_for_status()
        payload = response.json()
        self._access_token = payload["access_token"]
        self._expires_at = time.time() + payload.get("expires_in", 3600)
        return self._access_token

    def _collect(self, resource: str, params: dict[str, str | None], max_records: int | None = None) -> list[dict]:
        results: list[dict] = []
        url = f"{self.base_uri}/{resource.strip('/')}"
        while url:
            response = httpx.get(
                url,
                headers={"Authorization": f"Bearer {self._token()}"},
                params={key: value for key, value in params.items() if value},
                timeout=60,
            )
            response.raise_for_status()
            payload = response.json()
            results.extend(payload.get("value", []))
            if max_records and len(results) >= max_records:
                return results[:max_records]
            url = payload.get("@odata.nextLink")
            params = {}
        return results

    def list_properties(self, *, filter: str | None = None, select: list[str] | None = None, orderby: str | None = None, top: int = 1000, max_records: int | None = None) -> list[Property]:
        items = self._collect(
            "Property",
            {"$filter": filter, "$select": ",".join(select) if select else None, "$orderby": orderby, "$top": str(top)},
            max_records=max_records,
        )
        return [Property.model_validate(item) for item in items]

    def property_by_listing_key(self, listing_key: str, select: list[str] | None = None) -> Property | None:
        escaped = listing_key.replace("'", "''")
        items = self.list_properties(filter=f"ListingKey eq '{escaped}'", select=select, top=1, max_records=1)
        return items[0] if items else None

    def list_media_by_listing_key(self, listing_key: str) -> list[dict]:
        escaped = listing_key.replace("'", "''")
        items = self._collect(
            "Media",
            {
                "$filter": f"ResourceRecordKey eq '{escaped}'",
                "$select": "MediaURL,ImageOf,Order,MediaKey,MediaCategory,MediaType,MediaModificationTimestamp",
                "$orderby": "Order",
                "$top": "200",
            },
            max_records=200,
        )
        return [
            {
                "mediaUrl": item.get("MediaURL"),
                "imageOf": item.get("ImageOf"),
                "order": item.get("Order"),
                "mediaKey": item.get("MediaKey"),
                "mediaCategory": item.get("MediaCategory"),
                "mediaType": item.get("MediaType"),
                "modifiedAt": item.get("MediaModificationTimestamp"),
            }
            for item in items
        ]
