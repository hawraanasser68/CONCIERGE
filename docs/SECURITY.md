# Security

## Threat Model

This repo handles untrusted visitor input from embedded widgets and routes that input across multiple internal services. The main risks Owner C addresses are:

- prompt injection against the chat stack
- jailbreak attempts that try to bypass system or policy controls
- cross-tenant data leakage
- accidental storage of secrets or PII in logs, traces, or memory
- misuse of internal service-to-service APIs

The attacker model includes anonymous visitors, users with valid widget tokens, and scripts that send direct HTTP requests instead of using the browser widget.

## Security Boundaries

Security is layered. The classifier is a routing optimization, not the primary security wall.

- Platform rails are mandatory and apply to every tenant.
- Tenant rails may restrict behavior further but cannot weaken platform rails.
- Service-to-service authentication protects internal modelserver and guardrails endpoints.
- Tenant isolation is enforced outside Owner C by token verification and repository/database scoping.
- Redaction removes secrets and PII before data reaches logs, traces, or conversation memory.

## Platform Rails vs Tenant Rails

Platform rails are global controls for prompt injection, jailbreak attempts, cross-tenant probing, and PII handling. These controls are not tenant-configurable.

Tenant rails are narrower controls for allowed topics, blocked topics, and persona enforcement. They apply after platform rails and may only tighten behavior.

Current status: the guardrails service is still a lightweight stub. It enforces service-token auth and redaction but does not yet run full NeMo Guardrails policies.

## Prompt Injection and Jailbreaks

Prompt injection attempts try to override hidden instructions, reveal system prompts, or coerce the assistant into unsafe behavior. Jailbreak attempts try to break character, disable safeguards, or expose internal reasoning.

Owner C maintains red-team probes in:

- `backend/evals/redteam/injection.jsonl`

These cases are intended to verify that hostile instructions are blocked rather than followed.

## Cross-Tenant Leakage

Cross-tenant leakage is the highest-impact application risk. An attacker may ask for:

- another tenant's CMS content
- another tenant's leads
- another tenant's prompts or agent configuration
- data using a spoofed `tenant_id`

Owner C maintains cross-tenant probe cases in:

- `backend/evals/redteam/cross_tenant.jsonl`

These probes document expected fail-closed behavior and verify that references to other tenants never produce other-tenant data.

## Service-to-Service Authentication

Internal Owner C services require Bearer tokens loaded from Vault:

- `secret/svc/modelserver`
- `secret/svc/guardrails`

Requests without a valid service token must return `401`. Token values are never logged.

For local development only, the current stubs support environment-variable fallbacks when Vault bootstrap variables are absent:

- `MODELSERVER_TOKEN`
- `GUARDRAILS_TOKEN`

These fallbacks are for local smoke testing, not production deployment.

## Redaction Before Logs, Traces, and Memory

Redaction happens before sensitive content should be persisted anywhere downstream. The current lightweight utility redacts:

- `sk-ant-...` keys
- `sk-...` keys
- `Bearer ...` tokens
- `ghp_...` GitHub tokens
- `AKIA...` AWS access keys
- email addresses
- phone-like numbers

The intended rule is simple: raw secrets and PII should not land in logs, traces, or conversation memory after Owner C processing.

Reference assets:

- `backend/evals/redaction/cases.jsonl`
- `backend/evals/redaction/run.py`
- `backend/app/services/redaction.py`

## Fail-Closed Policy

The guardrails sidecar is a security component. If it is unavailable or returns a server error, the calling layer must fail closed rather than allow unguarded content through.

That means:

- no message should be treated as safe just because the sidecar is down
- a sidecar outage is a security failure, not a graceful-degradation path

## False-Positive Policy

When a platform rail blocks content, the visitor should receive a generic refusal rather than internal category details. False positives should be logged only with safe metadata: `tenant_id`, `session_id`, flagged categories, and timing; never message content or PII.

False-positive rate should be monitored and calibrated over time. Tenant rails may restrict behavior further, but they cannot weaken platform rails. Current guardrails are still stub/pass-through, so this section describes the target behavior for real rails rather than a completed NeMo policy implementation.

## Current Limitations

The current state is intentionally lightweight:

- `guardrails/server.py` is still a stub service
- red-team and redaction runners validate fixtures only, not full API-level enforcement
- full NeMo Guardrails flows are not implemented yet
- Presidio is not integrated yet
- platform and tenant rail policy execution is still future hardening work

Planned hardening remains aligned with the Owner C spec:

- real NeMo guardrails enforcement
- stronger PII handling beyond regex-only redaction
- fuller red-team coverage and CI gating
