"""Rootly API client.

Read-only: fetches incidents, alerts, and teams.
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
    RootlyAlert,
    RootlyIncident,
    RootlyTeam,
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
        acknowledged_at=_parse_date(attrs.get("acknowledged_at")),
        mitigated_at=_parse_date(attrs.get("mitigated_at")),
        resolved_at=_parse_date(attrs.get("resolved_at")),
        description=attrs.get("summary", "") or attrs.get("description", ""),
        services=_extract_services(attrs),
        teams=_extract_teams(attrs),
        raw=raw,
    )


def _extract_id_list(attrs: dict, key: str) -> list[str]:
    """Pull a list of IDs from an attributes field."""
    items = attrs.get(key) or []
    if isinstance(items, list):
        return [str(i) for i in items if i]
    return []


def _normalise_alert(raw: dict) -> RootlyAlert:
    attrs = raw.get("attributes", {})

    # Primary: attributes.incidents is an array of embedded incident objects
    incident_id = ""
    incidents_list = attrs.get("incidents") or []
    if isinstance(incidents_list, list) and incidents_list:
        first = incidents_list[0]
        if isinstance(first, dict):
            incident_id = str(first.get("id", ""))

    # Fallback: relationships.incident.data.id (older API shape)
    if not incident_id:
        rels = raw.get("relationships", {})
        inc_rel = rels.get("incident", {})
        inc_data = inc_rel.get("data") if isinstance(inc_rel, dict) else None
        if isinstance(inc_data, dict):
            incident_id = str(inc_data.get("id", ""))

    # Fallback: flat attributes.incident_id
    if not incident_id:
        incident_id = str(attrs.get("incident_id", "") or "")

    noise_val = attrs.get("noise") or ""
    return RootlyAlert(
        id=str(raw.get("id", "")),
        summary=attrs.get("summary", "") or attrs.get("title", ""),
        status=attrs.get("status", ""),
        source=attrs.get("source", ""),
        noise=str(noise_val),
        started_at=_parse_date(attrs.get("started_at")),
        ended_at=_parse_date(attrs.get("ended_at")),
        service_ids=_extract_id_list(attrs, "service_ids"),
        team_ids=_extract_id_list(attrs, "group_ids"),
        incident_id=incident_id,
        raw=raw,
    )


def _normalise_team(raw: dict) -> RootlyTeam:
    attrs = raw.get("attributes", {})
    return RootlyTeam(
        id=str(raw.get("id", "")),
        name=attrs.get("name", ""),
        slug=attrs.get("slug", ""),
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

    def fetch_alerts(
        self, incidents: list[RootlyIncident]
    ) -> list[RootlyAlert]:
        """Return triggered alerts by fetching /v1/incidents/{id}/alerts per incident.

        Rootly's global /v1/alerts endpoint ignores filter[incident_id], so the
        only reliable way to collect triggered alerts is via the per-incident
        sub-resource.  This makes one paginated request per incident (121 requests
        for 121 incidents) instead of paginating through tens of thousands of
        alerts globally.
        """
        seen_ids: set[str] = set()
        results: list[RootlyAlert] = []

        for i, incident in enumerate(incidents, 1):
            print(
                f"  [alerts] incident {i}/{len(incidents)} ({incident.id[:8]}...)    ",
                end="\r", flush=True,
            )
            try:
                for raw in _paginate(
                    f"/v1/incidents/{incident.id}/alerts",
                    self._headers,
                    {},
                    label="",
                ):
                    aid = str(raw.get("id", ""))
                    if aid in seen_ids:
                        continue
                    seen_ids.add(aid)
                    alert = _normalise_alert(raw)
                    # Stamp incident_id from the URL path if not in payload
                    if not alert.incident_id:
                        alert = RootlyAlert(
                            id=alert.id,
                            summary=alert.summary,
                            status=alert.status,
                            source=alert.source,
                            noise=alert.noise,
                            started_at=alert.started_at,
                            ended_at=alert.ended_at,
                            service_ids=alert.service_ids,
                            team_ids=alert.team_ids,
                            incident_id=incident.id,
                            raw=alert.raw,
                        )
                    results.append(alert)
            except Exception as exc:
                print(f"\n  Warning: could not fetch alerts for incident {incident.id}: {exc}")

        print(flush=True)
        return results

    def fetch_teams(self) -> list[RootlyTeam]:
        """Return all teams in the account."""
        seen_ids: set[str] = set()
        results: list[RootlyTeam] = []

        for raw in _paginate("/v1/teams", self._headers, {}, label="teams"):
            tid = str(raw.get("id", ""))
            if tid in seen_ids:
                continue
            seen_ids.add(tid)
            results.append(_normalise_team(raw))

        return results


def date_range_to_datetimes(preset: DateRangePreset) -> tuple[datetime, datetime]:
    """Convert a date-range preset to UTC (start, end) datetimes."""
    _DAYS = {"7d": 7, "30d": 30, "90d": 90}
    days = _DAYS[preset]
    end = datetime.now(timezone.utc)
    start = end - timedelta(days=days)
    return start, end
