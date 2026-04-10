# Security Policy

## Reporting a Vulnerability

**Do not open a public GitHub issue for security vulnerabilities.**

Report security issues via GitHub's private vulnerability reporting, or email the maintainer directly. Please include:

- Description of the vulnerability
- Steps to reproduce
- Potential impact
- Suggested fix (if any)

We will acknowledge receipt within 48 hours and aim to release a fix within 7 days for critical issues.

## Security Model

rootly-graphify is a **local development tool**. It fetches data from the Rootly API during collection, then all graph analysis runs locally with no further network calls.

### Threat Surface

| Vector | Mitigation |
|--------|-----------|
| API key exposure | Key read from `.env` or environment variable, masked in logs, never written to graph output |
| XSS in graph HTML output | `security.sanitize_label()` strips control characters, caps at 256 chars, and HTML-escapes all node labels and edge titles |
| Path traversal in MCP server | `security.validate_graph_path()` resolves paths and requires them to be inside `graphify-out/` |
| Encoding crashes on source files | All tree-sitter byte slices decoded with `errors="replace"` |

### What rootly-graphify does NOT do

- Does not store your API key in any output file
- Does not execute code from source files (tree-sitter parses ASTs — no eval/exec)
- Does not use `shell=True` in any subprocess call
- Does not make network calls during graph analysis — only during the initial Rootly API fetch
