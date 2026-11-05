# Security

- Payload persona, identity, permissions and IDs never grant access; server
  middleware must provide the context. Authorization is refreshed per request.
- Sessions bind to principal and persona and cannot restore permissions.
- Registry filtering is repeated at tool execution, and entity scopes are
  checked inside handlers immediately before reads.
- Strict Pydantic schemas bound message length, IDs, date windows and tool
  arguments. There is no unrestricted SQL/Python execution.
- Calls are capped and provider retries disabled. Failures never fall back to
  sample/mock data.
- Overall graph timeout is enforced at the request boundary. If a blocking
  provider call outlives that deadline, its worker thread cannot be forcibly
  interrupted; its eventual checkpoint is deleted. Retrieval handlers perform
  reads and existing inference only, with no mutation tools registered.
- LLM and LangSmith tracing are disabled by default. Tracing can send prompts
  and evidence to an external service; enable only under an approved policy.
- Historical energy sources are 2018. Anomaly outputs are synthetic 2019 and
  never evidence of verified real-world faults.
