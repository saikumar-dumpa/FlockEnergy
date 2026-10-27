# Flock Energy — Urja Meter Ops API

A small, read-only FastAPI wrapper that logs into the Urja Meter Ops portal, retains its session cookies, and parses server-rendered meter pages into JSON. The observed page flow and data format are documented in [PROTOCOL.md](PROTOCOL.md).

## Project structure

- `app/client.py` — portal login, cookie-backed requests, HTML/JSON parsing, and one session refresh retry.
- `app/models.py` — normalized API response models.
- `app/config.py` — environment-based settings.
- `app/main.py` — API routes, startup login, and error mapping.
- `tests/test_client.py` — isolated parser tests using synthetic HTML (not a mock portal service).
- `openapi.json` — checked-in OpenAPI 3.0 description.

## Install and run

Requires Python 3.10 or newer.

```powershell
cd flock-energy-api
py -m venv .venv
.\.venv\Scripts\Activate.ps1
py -m pip install -r requirements.txt
Copy-Item .env.example .env
```

Set `PORTAL_USER` and `PORTAL_PASS` in `.env` using the credentials provided to you. Do not commit `.env` or put credentials in source control. The application logs in on startup and fails explicitly if configuration or authentication is invalid.

```powershell
uvicorn app.main:app --reload --port 8000
```

Interactive API docs are available at `http://localhost:8000/docs`; the live schema at `http://localhost:8000/openapi.json`.

## Endpoints

- `GET /` — health and configured portal URL.
- `GET /api/v1/meters?page=1&limit=50` — paginated meter list.
- `GET /api/v1/meters/{meter_id}` — nameplate, installation, location, and hierarchy fields.
- `GET /api/v1/meters/{meter_id}/consumption?limit=100` — newest half-hourly consumption rows with timestamp, kWh, and kVAh.

Example requests:

```powershell
curl.exe "http://localhost:8000/api/v1/meters?page=1&limit=50"
curl.exe "http://localhost:8000/api/v1/meters/J100001"
curl.exe "http://localhost:8000/api/v1/meters/J100001/consumption"
```

Example detail response:

```json
{
  "meter_id": "J100001",
  "serial_no": "GE84132",
  "make": "L&T",
  "phase_type": "single",
  "installation_status": "Installed",
  "installation_type": "CT Operated",
  "dt_id": "DT-002",
  "zone": "Jaipur Zone 2 (Z-02)",
  "location_lat": 26.822,
  "location_long": 75.907,
  "full_hierarchy": "Jaipur Zone 2 (Z-02) > ... > DT-002"
}
```

## Assumptions and trade-offs

- The wrapper only reads from the portal; it does not expose or perform mutations.
- Portal login is a conventional form submission. The client retains cookies and carries hidden form fields (including any CSRF field) forward.
- The detail and consumption pages are server-rendered HTML; the wrapper parses the meter detail page rather than relying on a separate consumption API.
- Data uses the observed page labels, table headers, and `DD/MM/YYYY HH:MM` timestamps. Fields that cannot be found in the page are `null`.
- Startup login is intentionally eager so deployment configuration/auth failures are visible immediately. A request-time 401 triggers at most one re-login and retry.
- No cache is used, so responses reflect portal reads and avoid stale-data policy decisions; each API request may add portal load and latency.
- The service has no local index or background synchronization. It is sized for on-demand lookups rather than bulk analytics.

## Intentional omissions and next improvements

Not included: write operations, caching, bulk export, portal pagination traversal, deployment manifests, rate limiting, and a frontend. API pagination slices the rows currently returned by `/meters`; if the portal itself paginates its table, traversal should be added based on its actual controls. With more time, I would add fixtures from a redacted saved portal page, validate cookie expiry and pagination, add route-level tests, and evaluate caching or a local index against the real dataset.

See [PROTOCOL.md](PROTOCOL.md) for the portal investigation checklist and [REFLECTION.md](REFLECTION.md) for the take-home reflection. The checked-in [openapi.json](openapi.json) describes this wrapper API, not the legacy portal.

## Tests

```powershell
py -m pytest
```

Parser tests use synthetic response markup and make no requests to the portal.
