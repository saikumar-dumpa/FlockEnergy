"""Authenticated, read-only HTTP client for the Urja Meter Ops portal."""

from __future__ import annotations

from datetime import datetime
import re
from typing import Any
from urllib.parse import urljoin

import httpx
from bs4 import BeautifulSoup, Tag


class PortalError(RuntimeError):
    """Base exception for portal communication and parsing errors."""


class AuthenticationError(PortalError):
    """The portal rejected the login attempt."""


class SessionExpired(PortalError):
    """The portal session has expired and could not be refreshed."""


class PortalNotFound(PortalError):
    """The requested portal resource does not exist."""


class UrjaPortalClient:
    _DETAIL_LABELS = (
        "meter id",
        "serial no",
        "serial number",
        "make",
        "phase type",
        "installation status",
        "installation type",
    )

    def __init__(self, base_url: str, timeout: float = 15.0) -> None:
        self.base_url = base_url.rstrip("/") + "/"
               self.client = httpx.Client(
            follow_redirects=True,
            timeout=timeout,
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.9",
                "Accept-Encoding": "gzip, deflate, br",
                "Connection": "keep-alive",
                "Upgrade-Insecure-Requests": "1",
            },
        )
        self._credentials: tuple[str, str] | None = None

    def close(self) -> None:
        self.client.close()

    def login(self, username: str, password: str) -> bool:
        self._credentials = (username, password)
        login_url = urljoin(self.base_url, "login")
        try:
            page = self.client.get(login_url)
            page.raise_for_status()
        except httpx.HTTPError as exc:
            raise AuthenticationError(f"Unable to load portal login page: {exc}") from exc

        soup = BeautifulSoup(page.text, "html.parser")
        form = soup.find("form")
        if not isinstance(form, Tag):
            raise AuthenticationError("Portal login page did not contain a form.")

        form_data: dict[str, str] = {}
        for field in form.select("input, select, textarea"):
            name = str(field.get("name") or field.get("id") or field.get("autocomplete") or "").strip()
            if name:
                form_data[name] = str(field.get("value", ""))

        username_field = self._credential_field(
            form, ("username", "email", "user", "login"), "username"
        )
        password_field = self._credential_field(form, ("password", "pass"), "password")
        form_data[username_field] = username
        form_data[password_field] = password

        action = str(form.get("action") or login_url)
        try:
            response = self.client.post(urljoin(str(page.url), action), data=form_data)
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise AuthenticationError(f"Portal login request failed: {exc}") from exc

        result = BeautifulSoup(response.text, "html.parser")
        if self._has_login_error(result) or (
            result.find("form") is not None and self._looks_like_login(result)
        ):
            raise AuthenticationError("Portal did not accept the supplied credentials.")
        return True

    @staticmethod
    def _credential_field(form: Tag, choices: tuple[str, ...], fallback: str) -> str:
        for field in form.select("input, select, textarea"):
            input_type = str(field.get("type", "")).lower()
            if input_type in {"hidden", "submit", "button", "reset"}:
                continue

            for attribute in ("name", "id", "autocomplete", "placeholder"):
                value = str(field.get(attribute, "")).strip()
                if not value:
                    continue
                if any(choice in value.lower() for choice in choices):
                    return str(field.get("name") or field.get("id") or value)
        return fallback

    @staticmethod
    def _looks_like_login(soup: BeautifulSoup) -> bool:
        text = soup.get_text(" ", strip=True).lower()
        return "password" in text or "sign in" in text or "log in" in text

    @staticmethod
    def _has_login_error(soup: BeautifulSoup) -> bool:
        text = soup.get_text(" ", strip=True).lower()
        return any(
            phrase in text
            for phrase in (
                "invalid password",
                "invalid credentials",
                "invalid username",
                "invalid user",
                "incorrect password",
                "incorrect username",
                "wrong password",
                "wrong username",
                "login failed",
                "authentication failed",
                "username or password",
            )
        )

    def _get_authenticated(self, path: str) -> httpx.Response:
        response = self.client.get(urljoin(self.base_url, path.lstrip("/")))
        if response.status_code == 401 or self._is_login_redirect(response):
            if self._credentials is None:
                raise SessionExpired("Portal session expired and no login credentials are available.")
            self.login(*self._credentials)
            response = self.client.get(urljoin(self.base_url, path.lstrip("/")))
            if response.status_code == 401 or self._is_login_redirect(response):
                raise SessionExpired("Portal session expired after one re-login attempt.")
        if response.status_code == 404:
            raise PortalNotFound(f"Portal resource not found: {path}")
        try:
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise PortalError(f"Portal request failed for {path}: {exc}") from exc
        return response

    def _is_login_redirect(self, response: httpx.Response) -> bool:
        login_url = urljoin(self.base_url, "login")
        return response.url.path.rstrip("/") == httpx.URL(login_url).path.rstrip("/") or (
            self._looks_like_login(BeautifulSoup(response.text, "html.parser"))
        )

    def get_meter_details(self, meter_id: str) -> dict[str, Any]:
        response = self._get_authenticated(f"meters/{meter_id}")
        soup = BeautifulSoup(response.text, "html.parser")
        text = soup.get_text(" ", strip=True)
        labeled = self._extract_labeled_values(soup, text, self._DETAIL_LABELS)

        location_match = re.search(
            r"(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)", text
        )
        breadcrumbs = self._breadcrumb_text(soup)
        hierarchy_source = breadcrumbs or text
        dt_match = re.search(r"\bDT-\d+\b", hierarchy_source, re.IGNORECASE)
        zone_value = breadcrumbs.split(" > ", 1)[0] if breadcrumbs else None
        zone_match = re.search(
            r"\b([A-Za-z]+\s+Zone\s*\d+"
            r"(?:\s*\([A-Z0-9-]+\))?)",
            text,
            re.IGNORECASE,
        )

        return {
            "meter_id": labeled.get("meter id") or meter_id,
            "serial_no": labeled.get("serial no") or labeled.get("serial number"),
            "make": labeled.get("make"),
            "phase_type": labeled.get("phase type"),
            "installation_status": labeled.get("installation status"),
            "installation_type": labeled.get("installation type"),
            "dt_id": dt_match.group(0).upper() if dt_match else None,
            "zone": zone_value or (zone_match.group(1).strip() if zone_match else None),
            "location_lat": float(location_match.group(1)) if location_match else None,
            "location_long": float(location_match.group(2)) if location_match else None,
            "full_hierarchy": breadcrumbs or None,
        }

    @staticmethod
    def _extract_labeled_values(
        soup: BeautifulSoup,
        page_text: str,
        labels: tuple[str, ...],
    ) -> dict[str, str]:
        result: dict[str, str] = {}

        def normalize(value: str) -> str:
            return " ".join(value.lower().strip().rstrip(":").split())

        for label_tag in soup.select("dt, th, label, .label, [class*='label']"):
            label = normalize(label_tag.get_text(" ", strip=True))
            if label not in labels or label in result:
                continue
            sibling = label_tag.find_next_sibling()
            if sibling is not None:
                candidate = sibling.get_text(" ", strip=True)
                if candidate and normalize(candidate) not in labels:
                    result[label] = candidate
                    continue
            parent = label_tag.parent
            if isinstance(parent, Tag):
                parent_text = parent.get_text(" ", strip=True)
                prefix = label_tag.get_text(" ", strip=True)
                candidate = re.sub(
                    rf"^\s*{re.escape(prefix)}\s*:?\s*",
                    "",
                    parent_text,
                    flags=re.IGNORECASE,
                ).strip()
                if candidate and normalize(candidate) not in labels:
                    result[label] = candidate

        normalized_text = " ".join(page_text.split())
        label_pattern = "|".join(
            re.escape(label) for label in sorted(labels, key=len, reverse=True)
        )
        for label in labels:
            if label in result:
                continue
            match = re.search(
                rf"\b{re.escape(label)}\b\s*:?\s*(.*?)"
                rf"(?=\s+(?:{label_pattern})\b|$)",
                normalized_text,
                re.IGNORECASE,
            )
            if match:
                value = match.group(1).strip(" :")
                if value:
                    result[label] = value
        return result

    @staticmethod
    def _breadcrumb_text(soup: BeautifulSoup) -> str:
        breadcrumb = soup.select_one(
            "nav[aria-label*='breadcrumb' i], .breadcrumb, [class*='breadcrumb']"
        )
        if breadcrumb is None:
            return ""
        parts = [
            item.get_text(" ", strip=True)
            for item in breadcrumb.select("a, li, span")
            if item.get_text(" ", strip=True)
        ]
        if not parts:
            parts = [breadcrumb.get_text(" > ", strip=True)]
        return " > ".join(dict.fromkeys(parts))

    def list_meters(self, page: int = 1, limit: int = 50) -> list[dict[str, Any]]:
        if page < 1 or limit < 1:
            raise ValueError("page and limit must be positive integers")
        response = self._get_authenticated("meters")
        soup = BeautifulSoup(response.text, "html.parser")

        for table in soup.find_all("table"):
            headers = self._table_headers(table)
            if not self._has_meter_list_headers(headers):
                continue
            rows = table.select("tbody tr") or table.select("tr")
            records = [
                record
                for row in rows
                if (record := self._meter_from_row(row, headers)) is not None
            ]
            start = (page - 1) * limit
            return records[start : start + limit]
        raise PortalError("Could not locate the meter listing table in /meters.")

    @staticmethod
    def _table_headers(table: Tag) -> list[str]:
        header_row = table.select_one("thead tr")
        if header_row is None:
            header_row = table.find("tr")
        if header_row is None:
            return []
        return [
            " ".join(cell.get_text(" ", strip=True).lower().split())
            for cell in header_row.find_all(["th", "td"], recursive=False)
        ]

    @staticmethod
    def _has_meter_list_headers(headers: list[str]) -> bool:
        normalized = " ".join(headers)
        return (
            "meter" in normalized
            and "serial" in normalized
            and "make" in normalized
            and "phase" in normalized
            and "status" in normalized
            and re.search(r"\bdt\b", normalized) is not None
        )

    @staticmethod
    def _meter_from_row(row: Tag, headers: list[str]) -> dict[str, Any] | None:
        cells = row.find_all(["td", "th"], recursive=False)
        if not cells or (cells[0].name == "th"):
            return None
        values = [cell.get_text(" ", strip=True) for cell in cells]
        if len(values) < len(headers):
            return None
        values_by_header = dict(zip(headers, values))

        def value_for(fragment: str) -> str | None:
            value = next(
                (
                    value
                    for header, value in values_by_header.items()
                    if fragment in header
                ),
                "",
            )
            return value or None

        meter_cell = cells[0]
        meter_link = meter_cell.find("a", href=re.compile(r"/meters/"))
        meter_id = (
            meter_link.get_text(" ", strip=True)
            if isinstance(meter_link, Tag)
            else values[0]
        )
        if not meter_id:
            return None
        return {
            "meter_id": meter_id,
            "serial_no": value_for("serial"),
            "make": value_for("make"),
            "phase_type": value_for("phase"),
            "installation_status": value_for("status"),
            "dt_id": value_for("dt"),
        }

    def get_consumption(self, meter_id: str, limit: int = 100) -> list[dict[str, Any]]:
        if limit < 1:
            raise ValueError("limit must be a positive integer")
        response = self._get_authenticated(f"meters/{meter_id}")
        soup = BeautifulSoup(response.text, "html.parser")

        for table in soup.find_all("table"):
            headers = self._table_headers(table)
            timestamp_index = self._header_index(headers, ("timestamp",))
            kwh_index = self._header_index(headers, ("kwh",))
            kvah_index = self._header_index(headers, ("kvah",))
            if None in (timestamp_index, kwh_index, kvah_index):
                continue

            records: list[dict[str, Any]] = []
            rows = table.select("tbody tr") or table.select("tr")
            for row in rows:
                cells = row.find_all(["td", "th"], recursive=False)
                if not cells or cells[0].name == "th":
                    continue
                values = [cell.get_text(" ", strip=True) for cell in cells]
                try:
                    timestamp = datetime.strptime(
                        values[timestamp_index], "%d/%m/%Y %H:%M"
                    )
                    kwh = float(values[kwh_index].replace(",", ""))
                    kvah = float(values[kvah_index].replace(",", ""))
                except (IndexError, ValueError) as exc:
                    raise PortalError(
                        f"Invalid consumption row for meter {meter_id}: {values!r}"
                    ) from exc
                records.append(
                    {
                        "timestamp": timestamp.isoformat(),
                        "kwh": kwh,
                        "kvah": kvah,
                    }
                )
            records.sort(key=lambda record: record["timestamp"], reverse=True)
            return records[:limit]
        raise PortalError(
            f"Could not locate the TIMESTAMP/KWH/KVAH table for meter {meter_id}."
        )

    @staticmethod
    def _header_index(headers: list[str], keys: tuple[str, ...]) -> int | None:
        return next(
            (index for index, header in enumerate(headers) if any(key in header for key in keys)),
            None,
        )
