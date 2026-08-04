"""pi JSONL parse must not treat user prompt / auth errors as success."""

from __future__ import annotations

from bora.adapters.agent_pi import _parse_pi_jsonl

_AUTH_FAIL_STDOUT = """\
{"type":"session","version":3,"id":"x","timestamp":"2026-08-04T03:14:59.541Z","cwd":"/tmp"}
{"type":"agent_start"}
{"type":"turn_start"}
{"type":"message_start","message":{"role":"user","content":[{"type":"text","text":"Return ONLY JSON {\\"n\\": 2}"}],"timestamp":1}}
{"type":"message_end","message":{"role":"user","content":[{"type":"text","text":"Return ONLY JSON {\\"n\\": 2}"}],"timestamp":1}}
{"type":"message_start","message":{"role":"assistant","content":[],"api":"openai-completions","provider":"opencode","model":"glm-5.2","stopReason":"error","errorMessage":"401: {\\"type\\":\\"AuthError\\",\\"message\\":\\"Invalid API key.\\"}","timestamp":2}}
{"type":"message_end","message":{"role":"assistant","content":[],"api":"openai-completions","provider":"opencode","model":"glm-5.2","stopReason":"error","errorMessage":"401: {\\"type\\":\\"AuthError\\",\\"message\\":\\"Invalid API key.\\"}","timestamp":2}}
{"type":"turn_end","message":{"role":"assistant","content":[],"stopReason":"error","errorMessage":"401: {\\"type\\":\\"AuthError\\",\\"message\\":\\"Invalid API key.\\"}"},"toolResults":[]}
{"type":"agent_end","messages":[{"role":"user","content":[{"type":"text","text":"Return ONLY JSON {\\"n\\": 2}"}]},{"role":"assistant","content":[],"stopReason":"error","errorMessage":"401: {\\"type\\":\\"AuthError\\",\\"message\\":\\"Invalid API key.\\"}"}],"willRetry":false}
{"type":"agent_settled"}
"""


def test_auth_error_not_parsed_as_success_from_user_prompt() -> None:
    events, structured, text, usage, backend_err = _parse_pi_jsonl(_AUTH_FAIL_STDOUT)
    assert backend_err is not None
    assert "Invalid API key" in backend_err
    # Must NOT scrape {"n": 2} out of the user prompt.
    assert structured is None
    assert "Return ONLY JSON" not in text
    assert text == ""
    assert any(e.get("type") == "agent_end" for e in events)


def test_assistant_text_still_parsed() -> None:
    stdout = """\
{"type":"message_end","message":{"role":"user","content":[{"type":"text","text":"hi"}]}}
{"type":"message_end","message":{"role":"assistant","content":[{"type":"text","text":"{\\"n\\": 2}"}],"stopReason":"stop"}}
"""
    _events, structured, text, _usage, backend_err = _parse_pi_jsonl(stdout)
    assert backend_err is None
    assert text == '{"n": 2}'
    assert structured == {"n": 2}
