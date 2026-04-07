"""Rootly API client.

Read-only: fetches incidents and retrospectives (post-mortems).
Uses only stdlib (urllib) so no extra hard dependency is introduced.

Auth:  Authorization: Bearer <token>
Fmt:   Content-Type: application/vnd.api+json
Docs:  https://api.rootly.com/docs

NOTE: Rootly's API sits behind Cloudflare which blocks requests with no
User-Agent header (Error 1010). Every request must include one.
"""
from __future__ import annotations

import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Iterator
from datetime import datetime, timezone, timedelta
from typing import Any

from graphify.models_rootly import (
    DateRangePreset,
    RootlyIncident,
    RootlyRetrospective,
)

_BASE = "https://api.rootly.com"
_DEFAULT_PAGE_SIZE = 100   # max allowed by Rootly — fewer round-trips
_MAX_RETRIES = 3
_RETRY_STATUSES = {429, 500, 502, 503, 504}


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _build_headers(api_key: str) -> dict[str, str]:
    # User-Agent is required — Rootly's API sits behind Cloudflare which
    # returns 403 (Error 1010) for requests with no User-Agent header.
    return {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/vnd.api+json",
        "Accept": "application/vnd.api+json",
        "User-Agent": "graphify/0.3.6 (python-urllib)",
    }


def _get(url: str, headers: dict[str, str], params: dict[str, str] | None = None) -> dict:
    """HTTP GET with exponential-backoff retry on transient errors."""
    if params:
        url = url + "?" + urllib.parse.urlencode(params)

    for attempt in range(1, _MAX_RETRIES + 1):
        req = urllib.request.Request(url, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                body = resp.read()
                return json.loads(body)
        except urllib.error.HTTPError as exc:
            if exc.code in _RETRY_STATUSES and attempt < _MAX_RETRIES:
                wait = 2 ** attempt
                # Rootly rate-limit headers
                retry_after = exc.headers.get("Retry-After") or exc.headers.get("X-RateLimit-Reset")
                remaining = exc.headers.get("X-RateLimit-Remaining", "?")
                if retry_after:
                    try:
                        wait = int(retry_after)
                    except ValueError:
                        pass
                if exc.code == 429:
                    print(f"  Rootly rate limit hit (remaining: {remaining}) – waiting {wait}s (attempt {attempt}/{_MAX_RETRIES})")
                else:
                    print(f"  Rootly API {exc.code} – retrying in {wait}s (attempt {attempt}/{_MAX_RETRIES})")
                time.sleep(wait)
                continue
            if exc.code == 401:
                raise PermissionError(
                    "Rootly API: 401 Unauthorized – check your API key."
                ) from exc
            if exc.code == 403:
                body = ""
                try:
                    body = exc.read().decode("utf-8", errors="replace")
                except Exception:
                    pass
                if "1010" in body or "browser" in body.lower():
                    raise PermissionError(
                        "Rootly API: 403 blocked by Cloudflare (Error 1010). "
                        "This is a client User-Agent issue, not a key permission issue. "
                        "Update graphify to the latest version."
                    ) from exc
                raise PermissionError(
                    "Rootly API: 403 Forbidden – your key may not have access to this resource."
                ) from exc
            raise RuntimeError(f"Rootly API error {exc.code}: {exc.reason}") from exc
        except (urllib.error.URLError, OSError) as exc:
            if attempt < _MAX_RETRIES:
                time.sleep(2 ** attempt)
                continue
            raise RuntimeError(f"Network error contacting Rootly: {exc}") from exc
    raise RuntimeError("Rootly API: exceeded retry limit")


def _paginate(
    endpoint: str,
    headers: dict[str, str],
    base_params: dict[str, str],
    label: str = "",
) -> Iterator[dict]:
    """Yield every item from a paginated JSON:API collection endpoint.

    Rootly uses cursor-based pagination: the response's ``links.next`` contains
    the full URL for the next page; when absent, iteration stops.

    Prints a progress line per page so the user knows work is happening.
    """
    url = f"{_BASE}{endpoint}"
    params = {**base_params, "page[size]": str(_DEFAULT_PAGE_SIZE)}
    page_num = 0
    total_yielded = 0

    while url:
        page_num += 1
        data = _get(url, headers, params if params else None)
        items = data.get("data", [])
        total_count = data.get("meta", {}).get("total_count")

        # Print progress — do NOT show total_count as denominator since Rootly's
        # total_count reflects the unfiltered collection size, not the filtered result.
        tag = f"  [{label}] " if label else "  "
        print(
            f"{tag}page {page_num} — {total_yielded + len(items)} fetched so far…",
            end="\r",
            flush=True,
        )

        yield from items
        total_yielded += len(items)

        # After the first request params are encoded in links.next already
        params = {}
        links = data.get("links", {})
        next_url = links.get("next") or ""
        url = next_url

    # Final newline so the next print doesn't overwrite the progress line
    if page_num > 0:
        print(flush=True)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def validate_key(api_key: str) -> None:
    """Validate the API key by fetching a single incident.

    Uses /v1/incidents with page[size]=1 — directly tests the permission
    we actually need rather than an unrelated endpoint.

    Raises PermissionError on auth failure, RuntimeError on other errors.
    """
    if not api_key or not api_key.strip():
        raise ValueError("API key must not be empty.")
    headers = _build_headers(api_key)
    _get(f"{_BASE}/v1/incidents", headers, {"page[size]": "1"})


def _parse_date(value: Any) -> str:
    """Return a string date-time or empty string if missing."""
    if not value:
        return ""
    return str(value)


def _extract_services(attrs: dict) -> list[str]:
    """Pull service names from the incident attributes."""
    services = attrs.get("services", []) or []
    if isinstance(services, list):
        return [s.get("name", "") for s in services if isinstance(s, dict)]
    return []


def _extract_teams(attrs: dict) -> list[str]:
    teams = attrs.get("teams", []) or []
    if isinstance(teams, list):
        return [t.get("name", "") for t in teams if isinstance(t, dict)]
    return []


def _normalise_incident(raw: dict) -> RootlyIncident:
    attrs = raw.get("attributes", {})
    return RootlyIncident(
        id=str(raw.get("id", "")),
        title=attrs.get("title", "Untitled"),
        severity=(
            attrs.get("severity", {}).get("name", "")
            if isinstance(attrs.get("severity"), dict)
            else str(attrs.get("severity", ""))
        ),
        status=attrs.get("status", ""),
        started_at=_parse_date(attrs.get("started_at")),
        resolved_at=_parse_date(attrs.get("resolved_at")),
        description=attrs.get("summary", "") or attrs.get("description", ""),
        services=_extract_services(attrs),
        teams=_extract_teams(attrs),
        raw=raw,
    )


def _normalise_retrospective(raw: dict, incident_lookup: dict[str, RootlyIncident]) -> RootlyRetrospective:
    attrs = raw.get("attributes", {})
    rels = raw.get("relationships", {})
    incident_rel = rels.get("incident", {}).get("data", {})
    incident_id = str(incident_rel.get("id", attrs.get("incident_id", "")))
    incident = incident_lookup.get(incident_id)
    return RootlyRetrospective(
        id=str(raw.get("id", "")),
        incident_id=incident_id,
        incident_title=incident.title if incident else attrs.get("title", ""),
        status=attrs.get("status", ""),
        content=attrs.get("content", "") or "",
        created_at=_parse_date(attrs.get("created_at")),
        updated_at=_parse_date(attrs.get("updated_at")),
        started_at=_parse_date(attrs.get("started_at")),
        mitigated_at=_parse_date(attrs.get("mitigated_at")),
        resolved_at=_parse_date(attrs.get("resolved_at")),
        url=attrs.get("url", "") or "",
        raw=raw,
    )


class RootlyClient:
    """Thin read-only client for the Rootly v1 API."""

    def __init__(self, api_key: str) -> None:
        self._headers = _build_headers(api_key)

    def fetch_incidents(
        self, start_at: datetime, end_at: datetime
    ) -> list[RootlyIncident]:
        """Return incidents whose started_at falls within [start_at, end_at].

        Rootly's server-side date filters (filter[started_at_gte] etc.) do not
        reliably affect the response total_count and may be ignored. We instead
        sort by -started_at (newest first) and stop paginating as soon as we
        see a page whose oldest item predates our window — no wasted pages.
        """
        start_iso = start_at.strftime("%Y-%m-%dT%H:%M:%SZ")
        end_iso = end_at.strftime("%Y-%m-%dT%H:%M:%SZ")

        url = f"{_BASE}/v1/incidents"
        params: dict[str, str] = {
            "page[size]": str(_DEFAULT_PAGE_SIZE),
            "sort": "-started_at",
        }
        results: list[RootlyIncident] = []
        page_num = 0

        while url:
            page_num += 1
            data = _get(url, headers=self._headers, params=params if params else None)
            items = data.get("data", [])
            params = {}  # subsequent pages use links.next

            oldest_on_page = ""
            for raw in items:
                incident = _normalise_incident(raw)
                if not oldest_on_page or (incident.started_at and incident.started_at < oldest_on_page):
                    oldest_on_page = incident.started_at or oldest_on_page
                if incident.started_at and incident.started_at > end_iso:
                    continue  # future incident (shouldn't happen, but guard anyway)
                if incident.started_at and incident.started_at >= start_iso:
                    results.append(incident)

            print(
                f"  [incidents] page {page_num} — {len(results)} in window so far"
                + (f" (oldest on page: {oldest_on_page[:10]})" if oldest_on_page else ""),
                end="\r", flush=True,
            )

            # Early exit: once the oldest item on this page is before our window,
            # all subsequent pages are also before it (sorted newest-first).
            if oldest_on_page and oldest_on_page < start_iso:
                break

            next_url = data.get("links", {}).get("next") or ""
            url = next_url

        print(flush=True)  # clear the \r line
        return results

    def fetch_retrospectives_for_incidents(
        self, incidents: list[RootlyIncident]
    ) -> list[RootlyRetrospective]:
        """Return retrospectives linked to the given incidents.

        Strategy: fetch post_mortems filtered by the date window of the
        incidents (bulk, single paginated request) then match by incident ID.
        This is far faster than one request per incident.

        Falls back to per-incident fetching only if the bulk call fails.
        """
        if not incidents:
            return []

        incident_lookup = {i.id: i for i in incidents}
        incident_ids = set(incident_lookup.keys())

        # Derive window from the incidents we have
        started_dates = [i.started_at for i in incidents if i.started_at]
        if started_dates:
            start_iso = min(started_dates)
            end_iso = max(
                i.resolved_at or i.started_at
                for i in incidents
                if i.started_at
            )
        else:
            # Fallback: use a wide window
            now = datetime.now(timezone.utc)
            start_iso = (now - timedelta(days=90)).strftime("%Y-%m-%dT%H:%M:%SZ")
            end_iso = now.strftime("%Y-%m-%dT%H:%M:%SZ")

        # --- bulk fetch by date window ---
        try:
            results = self._fetch_retros_bulk(start_iso, end_iso, incident_lookup, incident_ids)
            if results:
                return results
        except RuntimeError as exc:
            print(f"  Bulk retrospective fetch failed ({exc}), falling back to per-incident fetch…")

        # --- fallback: one request per incident ---
        return self._fetch_retros_per_incident(incidents, incident_lookup)

    def _fetch_retros_bulk(
        self,
        start_iso: str,
        end_iso: str,
        incident_lookup: dict[str, RootlyIncident],
        incident_ids: set[str],
    ) -> list[RootlyRetrospective]:
        """Fetch all post_mortems in one paginated pass and filter by incident ID."""
        params: dict[str, str] = {
            "filter[created_at_gte]": start_iso,
            "sort": "-created_at",
        }
        seen_ids: set[str] = set()
        results: list[RootlyRetrospective] = []

        for raw in _paginate("/v1/post_mortems", self._headers, params, label="retrospectives"):
            rid = str(raw.get("id", ""))
            if rid in seen_ids:
                continue
            seen_ids.add(rid)
            retro = _normalise_retrospective(raw, incident_lookup)
            # Only keep retrospectives linked to our incidents
            if retro.incident_id in incident_ids:
                results.append(retro)

        return results

    def _fetch_retros_per_incident(
        self,
        incidents: list[RootlyIncident],
        incident_lookup: dict[str, RootlyIncident],
    ) -> list[RootlyRetrospective]:
        """Fallback: fetch post_mortems one incident at a time."""
        seen_ids: set[str] = set()
        results: list[RootlyRetrospective] = []
        total = len(incidents)

        for idx, incident in enumerate(incidents, 1):
            print(f"  [retrospectives] incident {idx}/{total}…", end="\r", flush=True)
            params = {"filter[incident_id]": incident.id, "sort": "-created_at"}
            try:
                for raw in _paginate("/v1/post_mortems", self._headers, params):
                    rid = str(raw.get("id", ""))
                    if rid in seen_ids:
                        continue
                    seen_ids.add(rid)
                    results.append(_normalise_retrospective(raw, incident_lookup))
            except RuntimeError:
                pass

        if total > 0:
            print(flush=True)
        return results


def date_range_to_datetimes(preset: DateRangePreset) -> tuple[datetime, datetime]:
    """Convert a date-range preset to UTC (start, end) datetimes."""
    _DAYS = {"7d": 7, "30d": 30, "90d": 90}
    days = _DAYS[preset]
    end = datetime.now(timezone.utc)
    start = end - timedelta(days=days)
    return start, end
