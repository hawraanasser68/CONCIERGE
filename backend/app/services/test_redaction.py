from app.services.redaction import redact


def test_redact_handles_empty_values():
    assert redact(None) == ""
    assert redact("") == ""


def test_redact_replaces_secrets_and_pii():
    text = (
        "Call me at +1 (555) 867-5309 or john@example.com. "
        "Bearer abc.def.ghi and sk-ant-secretvalue12345 and sk-secretvalue12345 "
        "plus ghp_abcdefghijklmnopqrstuvwxyz123456 and AKIA1234567890ABCDEF"
    )

    redacted = redact(text)

    assert "[REDACTED-PHONE]" in redacted
    assert "[REDACTED-EMAIL]" in redacted
    assert "[REDACTED-TOKEN]" in redacted
    assert "[REDACTED-ANTHROPIC-KEY]" in redacted
    assert "[REDACTED-APIKEY]" in redacted
    assert "[REDACTED-GITHUBTOKEN]" in redacted
    assert "[REDACTED-AWSKEY]" in redacted
    assert "john@example.com" not in redacted
    assert "867-5309" not in redacted
