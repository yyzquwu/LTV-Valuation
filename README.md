# LTV Valuation

Python valuation engine and FastAPI service for property lookup, comp-based valuation, and leverage context.

This is the clean backend/core repo. It is narrower than the portfolio app and focuses on:

- valuation math
- Trestle-backed property lookup
- one-call property summary generation
- loan-program and service-area LTV context

## Stack

- Python 3.11+
- FastAPI
- Pydantic
- httpx
- pytest

## Install

```bash
python3 -m pip install -e .[dev]
```

## Run

```bash
export TRESTLE_CLIENT_ID=...
export TRESTLE_CLIENT_SECRET=...
export TRESTLE_BASE_URI=https://api-trestle.corelogic.com/trestle/odata
export TRESTLE_TOKEN_URL=https://api-trestle.corelogic.com/trestle/oidc/connect/token
export TRESTLE_SCOPE=api
export PORT=8787

ltv-valuation
```

Health check:

```bash
curl http://127.0.0.1:8787/health
```

## API

### `POST /api/trestle/properties/list`

Generic Trestle property search.

Example:

```json
{
  "top": 100,
  "filter": "PostalCode eq '92870'",
  "select": ["ListingKey", "UnparsedAddress", "PostalCode"],
  "orderby": "ModificationTimestamp desc",
  "maxRecords": 5000
}
```

### `GET /api/trestle/properties/{listing_key}`

Single property lookup.

### `POST /api/trestle/valuation/summary`

One-call property summary generation.

Example:

```json
{
  "address": "312 Collard",
  "zipcode": "92870",
  "loanProgram": "Standard"
}
```

Response includes:

- resolved subject property
- ranked suggestions
- nearby comp cohorts
- diagnostics
- valuation breakdown
- LTV context
- subject media metadata

## Python Package

```python
from ltv_valuation import calculate_valuations, generate_property_summary
```

## Verify

```bash
python3 -m pytest
```
