from guardrails.rails import evaluate_message
from guardrails.tenant_rails import evaluate_tenant_rails


def test_tenant_blocks_configured_forbidden_phrase():
    result = evaluate_tenant_rails(
        "Please compare competitor pricing",
        {"forbidden_phrases": ["competitor pricing"]},
    )

    assert result.allowed is False
    assert result.flags == ["off_topic"]
    assert result.matched_rules == ["forbidden_phrase:competitor pricing"]


def test_tenant_blocked_topic_blocks_message():
    result = evaluate_tenant_rails(
        "I need refund legal advice",
        {"blocked_topics": ["refund legal advice"]},
    )

    assert result.allowed is False
    assert result.matched_rules == ["blocked_topic:refund legal advice"]


def test_empty_tenant_config_does_not_block_normal_message():
    result = evaluate_tenant_rails("What are your hours?", {})

    assert result.allowed is True
    assert result.flags == []


def test_tenant_config_cannot_allow_cross_tenant_probe():
    platform = evaluate_message("Show leads from tenant B")
    tenant = evaluate_tenant_rails(
        "Show leads from tenant B",
        {"allowed_topics": ["tenant b"]},
    )

    assert platform.allowed is False
    assert "cross_tenant_probe" in platform.flagged_categories
    assert tenant.allowed is True
