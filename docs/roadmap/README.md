# Roadmap

Design documents for work that has **not been implemented**. Everything here
describes what NEMOS should do, not what it does.

For current behaviour see [../workflow.md](../workflow.md) and
[../../ARCHITECTURE.md](../../ARCHITECTURE.md).

| Document | Proposes |
|---|---|
| [guardrail_architecture.md](guardrail_architecture.md) | A validation layer that catches misconfiguration before the expensive stages run, and classifies a finished run honestly instead of writing `.nemos_done` on exit code 0 |

Its section 0 — the failure inventory — is worth reading even though the rest is
speculative: those failure modes are real and present in the code today. The
user-facing summary lives under "Known limitations" in the
[README](../../README.md).
