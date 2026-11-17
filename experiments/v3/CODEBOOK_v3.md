# APIGUARD labelling codebook v3 (2026-11-17)

Label one endpoint (one path + method) from its OpenAPI design only. Answer each question; the endpoint is
**1 (risky)** if ANY question is "yes, clearly", otherwise **0**. Record the OWASP API Top 10 2023 categories that fired.

Changed from v2: **an endpoint that needs a login can still be 1.** Missing authentication is only one of the questions.
Public-by-design endpoints (login, signup, password-reset request, health, docs, public catalogue reads) are NOT risky
just because they have no login.

| Q | Question (yes → 1) | OWASP |
|---|---|---|
| Q1 BOLA | Reads/changes/deletes ONE object picked by an id/name in the path or query (user, account, order, file, message, vehicle …) and the object belongs to a user or tenant, with nothing in the design (scopes, `me`-style path, owner check described) that limits it to the caller's own objects. | API1 |
| Q2 Broken auth | Non-public operation with no security requirement; OR credentials/API key/token in the URL query; OR a login/OTP/token endpoint with no 429 or rate-limit header; OR HTTP basic over a plain http server. | API2 |
| Q3 Property-level | Response returns secrets or clearly sensitive fields (password, hash, token, card, SSN, other users' private data) that a client does not need; OR the request body lets the caller set privilege/ownership/money fields (role, isAdmin, balance, owner_id, price, status, verified) that are not marked readOnly. | API3 |
| Q4 Resource use | Returns an unbounded collection (no limit/page params) of user data; OR uploads/batch/expensive jobs with no size limit; OR auth endpoint with no rate limit (also Q2). | API4 |
| Q5 Function-level | Admin / management / role / permission / internal / debug function (path or summary says so) with no stronger scope than ordinary user operations, or with no security. | API5 |
| Q6 Business flow | Sensitive flow that is easy to automate (purchase, coupon, referral, vote, transfer, OTP) with no anti-automation in the design. | API6 |
| Q7 SSRF | Takes a URL / host / callback / webhook value that the server will fetch. | API7 |
| Q8 Misconfiguration | Plain http server for non-public data, or debug/stack-trace style endpoints exposed. | API8 |
| Q9 Inventory | Old/beta/test/internal version exposed next to the current one (v1 beside v3, /beta/, /test/). | API9 |
| Q10 Unsafe consumption | Forwards data to a third-party API or consumes third-party callbacks with no validation described. | API10 |

Rules of thumb
- Judge only what the spec shows. Do not assume protection that is not written down, but do not invent flaws either.
- Cloud-provider management APIs (Azure, AWS, Google) that use OAuth2 with scopes on every operation are usually 0,
  unless a question above clearly fires.
- When unsure, label 0 (precision matters for the gate).
