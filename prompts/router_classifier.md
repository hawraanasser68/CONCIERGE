<!-- Owner B -->
# Router — Classifier Label → Workflow Mapping

Developer reference: how the classifier's intent labels translate into routing decisions
inside `backend/app/services/router.py`.

| Intent | Confidence | Workflow | Cost |
|--------|-----------|----------|------|
| `spam` | any | Drop — generic refusal, no DB write, no Redis log | 0 LLM calls |
| `faq` | ≥ 0.80 | RAG workflow: 1 embed call + ANN search + 1 LLM call (no tool loop) | ~cheap |
| `lead` | ≥ 0.80 | Direct lead: 1 LLM call → `capture_lead` tool (1 iteration max) | ~cheap |
| `escalate` | ≥ 0.80 | Direct escalate: 1 LLM call → `escalate` tool (1 iteration max) | ~cheap |
| `ambiguous` | any | Full agent: bounded tool loop, up to `min(config.max_tool_iterations, 10)` | expensive |
| any | < 0.80 | Treated as `ambiguous` regardless of label | expensive |

## Fail behaviours

- **Classifier 5xx / timeout** → `ClassifyResult(intent="ambiguous", confidence=0.0)` — fail open.
  The agent handles it; experience degrades but the visitor still gets a response.
- **Guardrails 5xx** → raise `GuardrailsUnavailableError` → HTTP 503 — fail closed.
  A guardrails failure is a security failure; never allow a message through.

## Efficiency metric (B-035)

The structured log event emitted by `router.py` on every turn:

```json
{
  "event": "router_decision",
  "tenant_id": "uuid",
  "intent": "faq",
  "confidence": 0.93,
  "routed_to": "workflow:faq"
}
```

`routed_to` values: `"workflow:faq"`, `"workflow:lead"`, `"workflow:escalate"`, `"agent"`.

Aggregate `routed_to != "agent"` to measure % turns off the expensive agent path.
