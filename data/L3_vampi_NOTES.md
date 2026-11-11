# VAmPI ground truth: how each row was decided (FINAL; made by an LLM from the README + source, mapped to OWASP API Top 10 2023; no human review)
Sources: VAmPI README "List of Vulnerabilities" (9 items, no endpoint mapping) and the handler code in
api_views/users.py and api_views/books.py (github.com/erev0s/VAmPI), read 2026-11-06.
label=1: the handler has a flaw (in vulnerable mode or in all modes).  design_visible=1: the flaw can be seen from the spec alone.

| Endpoint | label | Why (from the source) | design_visible |
|---|---|---|---|
| GET /users/v1/_debug | 1 | No auth; returns all users incl. password/admin (README: excessive data exposure) | 1 no security |
| GET /users/v1 | 1 | No token check; lists all users | 1 no security |
| GET /users/v1/{username} | 1 | No token check; any user's details; enumeration (200 vs 404) | 1 no security |
| POST /users/v1/register | 1 | Mass assignment of `admin` (vuln mode); user enumeration | 0 (`admin` is not in the spec) |
| POST /users/v1/login | 1 | Username/password enumeration messages (vuln mode); no rate limit; weak JWT key (README) | 0 |
| PUT /users/v1/{username}/email | 1 | ReDoS regex (vuln mode) | 0 |
| PUT /users/v1/{username}/password | 1 | Any authenticated user can change another user's password (vuln mode) | 0 |
| GET /books/v1/{book_title} | 1 | BOLA: book looked up by title only, not by owner (vuln mode) | 0 |
| GET /books/v1 | 1 | Handler never validates a token | 1 no security |
| GET /createdb | 1 | JUDGEMENT CALL. Unauthenticated, destroys and recreates the DB. It is a setup helper, not in the README list | 1 |
| DELETE /users/v1/{username} | 0 | Admin check present; only indirectly exploitable through mass assignment | 0 |
| GET /me, POST /books/v1, GET / | 0 | No flaw found in the handler | 0 |

## Decisions (final)
1. /createdb, /books/v1, /users/v1 stay label=1: real weaknesses in the code (no auth on a destructive/listing handler), mapped to OWASP API2/API5. The README does not list them, so the paper reports L3 for all rows and for the design-visible subset; a README-only variant has 7 flaw endpoints.
2. README's SQL injection item is not tied to a single route, so no row is labelled for it.
3. Categories are the LLM's mapping to OWASP API Top 10 2023.
4. crAPI was added on 2026-11-10 (15 flaw endpoints, from the 15 documented challenges).
