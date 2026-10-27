# Urja Meter Ops portal protocol

## Observed flow and pages

The portal was inspected in a normal signed-in browser session using the assignment-provided operator account. The meter listing is at `GET /meters` and was reported to show 403 meter entries. Selecting meter `J100001` opens `GET /meters/J100001`.

The `J100001` detail page renders three relevant areas in the HTML:

- **Nameplate**: Meter ID (`J100001`), Serial No (`GE84132`), Make (`L&T`), Phase Type (`single`), Installation Status (`Installed`), and Installation Type (`CT Operated`).
- **Location**: latitude and longitude rendered together as a comma-separated pair; the supplied example is `26.822..., 75.907...`.
- **Network hierarchy**: a breadcrumb from `Jaipur Zone 2 (Z-02)` through intermediate nodes to `DT-002`.
- **Consumption**: a half-hourly table with `TIMESTAMP`, `KWH`, and `KVAH`. The timestamp format is `DD/MM/YYYY HH:MM`; an example record is `23/06/2026 23:30`, `42594.05` kWh, and `46001.58` kVAh.

The reported data is server-rendered in the meter page HTML; no separate consumption XHR/API was observed during that inspection. The wrapper therefore requests the meter page and parses the relevant table with BeautifulSoup. Table headers are used to locate columns rather than relying on column positions.

## Authentication and session

Login is performed through the portal's browser login flow. The Python client performs a GET of `/login`, carries named hidden form inputs forward (including a CSRF field if present), posts the credentials to the form action, and retains cookies using one `httpx.Client`. Cookie name, exact login field names, and CSRF parameter name were not captured in the observations supplied for this implementation, so the client discovers the form controls rather than hard-coding them. It retries a protected request once after detecting an expired session.

## API interpretation

- `GET /meters` supplies listing rows expected to include METER, SERIAL, MAKE, PHASE, STATUS, and DT columns. The wrapper normalizes these into meter ID, serial, make, phase, installation status, and DT ID.
- `GET /meters/{meter_id}` supplies nameplate, location, hierarchy, and consumption data.
- Consumption timestamps are parsed as `%d/%m/%Y %H:%M`, returned as ISO 8601 local/naive timestamps, sorted newest first, and capped at 100 records by default.
- `L&T` is decoded from its HTML entity by the HTML parser.

## Remaining implementation checks

The page layout and example values above reflect the portal inspection details supplied for this implementation. Before production use, verify against a fresh authenticated browser session:

- Exact login form names, cookie name, redirects, and session-expiry status.
- Exact HTML wrappers around the nameplate labels, coordinate text, and breadcrumb; the parser supports common label/value pairs and breadcrumb markup.
- Whether `/meters` returns all 403 rows or a portal-paginated subset. API `page`/`limit` currently slices the rows returned by that page and does not follow portal pagination controls.
- Whether detail pages contain more than 100 consumption records and whether timestamps have an explicit timezone. The current API intentionally returns the newest 100 with no timezone offset.

Do not copy credential values or session-cookie values into this document or source control. The client is read-only and does not replay mutation requests.
