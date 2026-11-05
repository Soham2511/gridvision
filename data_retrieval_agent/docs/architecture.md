# Independent Data Retrieval Agent architecture

The module does not import or depend on `backend.app.ai`. It receives the
existing Customer Gold, forecast, segmentation, and anomaly services through
dependency injection. It does not own ETL, duplicate model features, execute
arbitrary SQL/Python, or load arbitrary artifact paths.

The Flask blueprint validates requests and delegates to the agent. A trusted
host identity adapter must produce an immutable context. The registry exposes
only tools whose source and permission are available; each tool repeats the
permission and entity check at execution. A bounded LangGraph workflow plans
minimal retrieval, executes independent calls in parallel, permits one
conditional follow-up round, validates tool output, and generates a response
from evidence. The response layer falls back to exact serialized values if the
LLM changes numeric values.

LangGraph `InMemorySaver` and an owner-bound TTL session manager provide
session-only memory. Sessions are process-local and lost on restart. Multi-worker
production requires an approved shared checkpointer/session store before
deployment. No permanent cross-session memory is created.

The agent and LLM default to disabled. There is no identity integration in the
repository, so the API returns 401 until the host injects a trusted
`data_retrieval_identity_resolver`. Company/equipment/operating-hour data are
not in the repository; those capabilities report unavailable.
