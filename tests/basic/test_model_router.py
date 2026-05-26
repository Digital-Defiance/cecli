from bright_vision_core.model_router import (
    ModelRouterConfig,
    classify_prompt,
    estimate_prompt_tokens,
    should_escalate_fast_turn,
)


def test_classify_low_tokens_fast_keyword():
    router = ModelRouterConfig(
        enabled=True,
        fast_model="ollama_chat/small",
        heavy_model="ollama_chat/big",
    )
    d = classify_prompt(
        "Rename the button label to Save",
        estimated_tokens=500,
        router=router,
        heavy_model_name="ollama_chat/big",
    )
    assert d.tier == "fast"
    assert d.model_name == "ollama_chat/small"


def test_classify_architect_heavy():
    router = ModelRouterConfig(
        enabled=True,
        fast_model="ollama_chat/small",
        heavy_model="ollama_chat/big",
    )
    d = classify_prompt(
        "Refactor the race condition in the session pool",
        estimated_tokens=800,
        router=router,
        heavy_model_name="ollama_chat/big",
    )
    assert d.tier == "heavy"


def test_classify_high_tokens_heavy():
    router = ModelRouterConfig(
        enabled=True,
        fast_model="ollama_chat/small",
        heavy_model="ollama_chat/big",
        token_heavy_min=12_000,
    )
    d = classify_prompt(
        "fix typo",
        estimated_tokens=15_000,
        router=router,
        heavy_model_name="ollama_chat/big",
    )
    assert d.tier == "heavy"
    assert "tokens>=" in d.reasons[0]


def test_escalate_when_fast_no_edits():
    router = ModelRouterConfig(enabled=True, fast_model="a", heavy_model="b")
    decision = classify_prompt(
        "implement the login form",
        estimated_tokens=800,
        router=router,
        heavy_model_name="b",
        force_tier="fast",
    )
    assert should_escalate_fast_turn(
        decision,
        router=router,
        user_message="implement the login form",
        edited_files=[],
        assistant_text="ok",
    )


def test_estimate_tokens_with_files():
    assert estimate_prompt_tokens("hello", files_in_chat=2) > estimate_prompt_tokens("hello")
