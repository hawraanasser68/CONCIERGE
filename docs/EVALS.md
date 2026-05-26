# Evaluations

## Owner C — Classifier

The router contract exposed to the repo is `spam`, `faq`, `lead`, `escalate`, and `ambiguous`. Exported notebook labels `question` and `unknown_or_agent` are normalized here to `faq` and `ambiguous`.

### Public test set

| Model | Macro-F1 | spam F1 | faq F1 | lead F1 | escalate F1 | ambiguous F1 | Wrong direct routes |
|---|---:|---:|---:|---:|---:|---:|---:|
| Classical joblib | 0.9836 | 0.9831 | 0.9896 | 0.9658 | 0.9829 | 0.9966 | 0 |
| DL ONNX baseline | 0.9904 | 1.0000 | 0.9932 | 0.9795 | 0.9793 | 1.0000 | 2 |
| LLM zero-shot | pending | pending | pending | pending | pending | pending | pending |

### Final product golden set

| Model | Macro-F1 | spam F1 | faq F1 | lead F1 | escalate F1 | ambiguous F1 | Wrong direct routes |
|---|---:|---:|---:|---:|---:|---:|---:|
| Classical joblib | 0.8000 | 0.7500 | 0.8000 | 0.7692 | 0.8235 | 0.8571 | 0 |
| DL ONNX baseline | 0.7202 | 0.6667 | 0.7273 | 0.7200 | 0.7500 | 0.7368 | 3 |

### Interpretation

- Classical model ships.
- DL ONNX remains a comparison baseline only.
- DL was rejected because it produced high-confidence wrong direct routes, which is the failure mode that matters most for a router.
- The modelserver runtime threshold is `0.80`. The `0.75` value from Colab is retained only as the experimental threshold selected during offline evaluation.
- The classifier is a router, not the security boundary. Guardrails, auth, tenant isolation, and redaction remain the actual control plane for abuse and data-protection failures.
