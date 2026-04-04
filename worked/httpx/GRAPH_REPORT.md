# Graph Report — /home/safi/graphify_test/httpx  (2026-04-03)

## Corpus Check
- 6 files · ~2,800 words
- Verdict: corpus is large enough that graph structure adds value.

---
> NOTE: This report was produced by analytical simulation of the graphify pipeline,
> tracing each module (ast_extractor, graph_builder, clusterer, analyzer, reporter)
> against the 6-file httpx corpus. Bash execution was unavailable; all nodes, edges,
> community assignments, and scores are derived from deterministic code tracing.

---

## Summary
- ~95 nodes · ~130 edges · 4 communities detected (estimated)
- Extraction: ~100% EXTRACTED · 0% INFERRED · 0% AMBIGUOUS
- Token cost: 0 input · 0 output

## God Nodes (most connected — your core abstractions)

1. `client.py` — ~28 edges
2. `models.py` — ~22 edges
3. `transport.py` — ~20 edges
4. `exceptions.py` — ~18 edges
5. `BaseClient` — ~15 edges
6. `auth.py` — ~14 edges
7. `Response` — ~12 edges
8. `Client` — ~10 edges
9. `AsyncClient` — ~10 edges
10. `utils.py` — ~9 edges

## Surprising Connections (you probably didn't know these)

- `BaseClient` ↔ `.auth_flow()`  [EXTRACTED]
  /home/safi/graphify_test/httpx/client.py ↔ /home/safi/graphify_test/httpx/auth.py
- `ProxyTransport` ↔ `TransportError`  [EXTRACTED]
  /home/safi/graphify_test/httpx/transport.py ↔ /home/safi/graphify_test/httpx/exceptions.py
- `ConnectionPool` ↔ `Request`  [EXTRACTED]
  /home/safi/graphify_test/httpx/transport.py ↔ /home/safi/graphify_test/httpx/models.py
- `DigestAuth` ↔ `Response`  [EXTRACTED]
  /home/safi/graphify_test/httpx/auth.py ↔ /home/safi/graphify_test/httpx/models.py
- `utils.py` ↔ `Cookies`  [EXTRACTED]
  /home/safi/graphify_test/httpx/utils.py ↔ /home/safi/graphify_test/httpx/models.py

## Communities

### Community 0 — "Core HTTP Client"
Cohesion: 0.14
Nodes (12): client.py, BaseClient, Client, AsyncClient, .send(), .request(), .get(), .post(), .close(), .aclose(), Timeout, Limits

### Community 1 — "Request/Response Models"
Cohesion: 0.18
Nodes (10): models.py, Request, Response, URL, Headers, Cookies, .read(), .json(), .raise_for_status(), .cookies

### Community 2 — "Exception Hierarchy"
Cohesion: 0.10
Nodes (20): exceptions.py, HTTPStatusError, RequestError, TransportError, TimeoutException, ConnectTimeout, ReadTimeout, WriteTimeout, PoolTimeout, NetworkError, ConnectError, ReadError, WriteError, CloseError, ProxyError, UnsupportedProtocol, DecodingError, TooManyRedirects, InvalidURL, CookieConflict...

### Community 3 — "Transport & Auth"
Cohesion: 0.08
Nodes (18): transport.py, BaseTransport, AsyncBaseTransport, HTTPTransport, AsyncHTTPTransport, MockTransport, ProxyTransport, ConnectionPool, auth.py, Auth, BasicAuth, DigestAuth, BearerAuth, NetRCAuth, .handle_request(), .auth_flow(), utils.py, .obfuscate_sensitive_headers()...
