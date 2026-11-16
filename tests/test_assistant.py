from narrow.assistant import LocalAssistant


def test_quick_reply_is_friendly_and_does_not_need_retrieval():
    assert LocalAssistant.quick_reply("hello") == (
        "Hello! I’m Narrow. Add a file or article, then ask me anything about its contents."
    )
    assert LocalAssistant.quick_reply("hello Narrow")
    assert LocalAssistant.quick_reply("how are you")
    assert LocalAssistant.quick_reply("who are you")
    assert LocalAssistant.quick_reply("something specific") is None
    assert LocalAssistant.is_casual("what music do you like") is True
    assert LocalAssistant.is_casual("what is CVE-2024-1234") is False


def test_answer_returns_abstention_without_evidence():
    result = LocalAssistant().answer("What is this?", {"passages": [], "abstain": True})

    assert result["abstain"] is True
    assert "strong enough evidence" in result["answer"]


def test_answer_falls_back_to_evidence_when_local_model_is_unavailable():
    assistant = LocalAssistant(base_url="http://127.0.0.1:1/v1", timeout=1)
    result = assistant.answer(
        "What happened?",
        {"passages": [{"id": "report#summary", "text": "The test completed.", "score": 0.9}], "abstain": False},
    )

    assert result["model_error"]
    assert "[E1]" in result["answer"]
    assert "The test completed." in result["answer"]
