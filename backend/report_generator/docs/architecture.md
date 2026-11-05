# JSON report generator architecture

The report generator is an isolated Flask feature under
`backend/report_generator`. It accepts bounded arbitrary JSON, inventories the
structure, calculates deterministic metrics, asks a configured LLM for dynamic
report text and section titles, validates that text, and renders one validated
document to HTML and optionally PDF. It does not use LangGraph or call existing
domain-specific AI/report routes.

## Data flow

1. The API resolves a trusted identity through the configured host callback.
2. A transport-independent parser enforces byte, nesting, node, string, and
   instruction limits; rejects duplicate keys and non-finite values.
3. `JSONStructureAnalyzer` describes paths, types, arrays, null/missing values,
   date candidates, and possible shared-record grouping dimensions.
4. `DeterministicAnalyticsEngine` computes statistics within each exact path
   and grouped comparison tables for compatible fields in arrays of objects.
   Each metric records its source path, method, sample count, and exclusions.
5. A configured provider receives user instructions separately from input
   data. Strings inside that data are marked untrusted. The provider produces
   only narrative and dynamic section structure; Python creates metric and
   comparison tables from authoritative calculations.
6. Pydantic validates the report, then Jinja2 (autoescaped) and ReportLab render
   it. PDF failure preserves the HTML artifact and yields `partial` status.
7. Metadata uses the existing `AI_DATABASE_PATH` in an isolated table.
   Artifacts use the existing private artifact store. Owner keys are HMACs of
   identities returned by the trusted host callback.

## LLM provider

`ollama` uses the local Ollama `/api/chat` endpoint and needs no API key. The
development configuration defaults to `gemma3:1b`. `hosted` and `huggingface`
use OpenAI-compatible Chat Completions endpoints via the Python standard
library. Hosted providers receive report input data; use a provider whose data
handling is approved for that data.

The implementation checks generated prose for numeric literals that do not
appear in source values or deterministic calculations. This is a conservative
guard, not a proof that every qualitative statement is true. Review generated
reports before relying on them for consequential decisions.

## Authorization and storage

The host application must set `REPORT_GENERATOR_IDENTITY_RESOLVER` to a trusted
callable accepting the Flask request and returning a stable authenticated
principal string. Missing, invalid, or failing resolvers deny report generation
and retrieval. No authentication provider is created by this module.

Report metadata and artifact IDs are stored in the existing AI SQLite database
and private artifact root. The submitted JSON and full prompts are not persisted
or logged. Report cleanup/retention is an operator responsibility until a
project-wide retention policy is configured.
