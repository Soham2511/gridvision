# API

Prefix: `/api/v1/data-retrieval-agent`. Every endpoint requires a host-injected
`data_retrieval_identity_resolver(request)` returning an
`AuthenticatedRequestContext`; configure it as a callable
`DATA_RETRIEVAL_IDENTITY_RESOLVER` on the Flask config class, or install it in
`app.extensions` after app creation. Missing/unverified identity returns 401.

| Method | Path | Behavior |
|---|---|---|
| POST | `/sessions` | Start owner-bound session; optional informational `{ "label": "..." }`. |
| POST | `/sessions/{id}/messages` | Continue with `{ "message": "..." }`; answer, source refs, clarification and availability returned. |
| GET | `/sessions/{id}` | Owner-visible session metadata only. |
| DELETE | `/sessions/{id}` | End session and clear checkpoint. |

Errors use standard GridVision JSON responses: 401 auth, 404 absent or
foreign-owned session, 422 invalid input, 503 disabled/unavailable model or
agent, 504 timeout. Sessions are currently in-memory and worker-local.
