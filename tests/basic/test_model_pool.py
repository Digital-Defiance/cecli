from bright_vision_core.model_router import ModelPoolEntry, resolve_model_pool


def test_resolve_pool_priority_order():
    pool = [
        ModelPoolEntry(model="ollama_chat/fast-a", tier="fast", enabled=False),
        ModelPoolEntry(model="ollama_chat/fast-b", tier="fast", enabled=True),
        ModelPoolEntry(model="ollama_chat/heavy-x", tier="heavy", enabled=True),
    ]
    fast, heavy = resolve_model_pool(
        pool,
        session_heavy="ollama_chat/session",
        fallback_fast="",
        fallback_heavy=None,
    )
    assert fast == "ollama_chat/fast-b"
    assert heavy == "ollama_chat/heavy-x"


def test_empty_heavy_row_uses_session():
    pool = [
        ModelPoolEntry(model="ollama_chat/fast", tier="fast", enabled=True),
        ModelPoolEntry(model="", tier="heavy", enabled=True),
    ]
    fast, heavy = resolve_model_pool(
        pool,
        session_heavy="ollama_chat/session",
    )
    assert fast == "ollama_chat/fast"
    assert heavy == "ollama_chat/session"
