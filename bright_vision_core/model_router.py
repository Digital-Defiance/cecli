"""
Local Ollama model tiering: classify prompts and pick fast vs heavy models.

Security: only uses model names supplied in config (Settings / session create) —
no runtime fetch of arbitrary models from the network.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from typing import Any, Literal

RouteTier = Literal["fast", "heavy"]

# Intent signals (case-insensitive word boundaries).
_HEAVY_PATTERNS = re.compile(
    r"\b("
    r"architect(?:ure|ural)?|refactor|rewrite|migrate|migration|"
    r"race\s+condition|deadlock|concurrency|distributed|microservice|"
    r"security|vulnerability|root\s+cause|design\s+review|"
    r"performance|scalability|profil(?:e|ing)|"
    r"from\s+scratch|greenfield|system\s+design"
    r")\b",
    re.IGNORECASE,
)

_FAST_PATTERNS = re.compile(
    r"\b("
    r"rename|typo|whitespace|format(?:ting)?|lint|prettier|"
    r"color|colour|style|css|spacing|margin|padding|"
    r"label|tooltip|copy|wording|comment(?:s)?|"
    r"tweak|ui\s+text|button\s+text"
    r")\b",
    re.IGNORECASE,
)

_CODE_TASK = re.compile(
    r"\b(implement|add|fix|create|update|change|patch|write|build)\b",
    re.IGNORECASE,
)


@dataclass
class ModelPoolEntry:
    model: str
    tier: RouteTier
    enabled: bool = True


def resolve_model_pool(
    pool: list[ModelPoolEntry],
    *,
    session_heavy: str,
    fallback_fast: str = "",
    fallback_heavy: str | None = None,
) -> tuple[str, str]:
    """Pick first enabled fast/heavy from hopper order; empty heavy model id → session_heavy."""
    fast = fallback_fast.strip()
    heavy = (fallback_heavy or "").strip() or session_heavy
    for entry in pool:
        if not entry.enabled:
            continue
        name = entry.model.strip()
        if entry.tier == "fast" and name and not fast:
            fast = name
        elif entry.tier == "heavy":
            if name:
                heavy = name
            else:
                heavy = session_heavy
    return fast, heavy


@dataclass
class ModelRouterConfig:
    enabled: bool = False
    fast_model: str = ""
    heavy_model: str | None = None
    model_pool: list[ModelPoolEntry] = field(default_factory=list)
    token_fast_max: int = 4_096
    token_heavy_min: int = 12_000
    keep_alive_fast: int | str = 300
    keep_alive_heavy: int | str = 0
    escalate_on_failure: bool = True

    @classmethod
    def from_payload(cls, raw: dict[str, Any] | None) -> ModelRouterConfig | None:
        if not raw:
            return None
        enabled = bool(raw.get("enabled"))
        if not enabled:
            return cls(enabled=False)
        pool_raw = raw.get("model_pool") or []
        pool: list[ModelPoolEntry] = []
        if isinstance(pool_raw, list):
            for item in pool_raw:
                if not isinstance(item, dict):
                    continue
                tier = item.get("tier")
                if tier not in ("fast", "heavy"):
                    continue
                pool.append(
                    ModelPoolEntry(
                        model=str(item.get("model") or ""),
                        tier=tier,
                        enabled=bool(item.get("enabled", True)),
                    )
                )
        fallback_fast = str(raw.get("fast_model") or "").strip()
        fallback_heavy = str(raw.get("heavy_model") or "").strip() or None
        session_heavy = fallback_heavy or fallback_fast or ""
        if pool:
            fast, heavy = resolve_model_pool(
                pool,
                session_heavy=session_heavy or fallback_fast,
                fallback_fast=fallback_fast,
                fallback_heavy=fallback_heavy,
            )
        else:
            fast, heavy = fallback_fast, fallback_heavy or fallback_fast
        if not fast:
            return None
        return cls(
            enabled=True,
            fast_model=fast,
            heavy_model=heavy or None,
            model_pool=pool,
            token_fast_max=int(raw.get("token_fast_max") or 4_096),
            token_heavy_min=int(raw.get("token_heavy_min") or 12_000),
            keep_alive_fast=raw.get("keep_alive_fast", 300),
            keep_alive_heavy=raw.get("keep_alive_heavy", 0),
            escalate_on_failure=bool(raw.get("escalate_on_failure", True)),
        )

    @classmethod
    def from_env(cls) -> ModelRouterConfig | None:
        if os.environ.get("BRIGHT_VISION_MODEL_ROUTER", "").strip() not in (
            "1",
            "true",
            "yes",
            "on",
        ):
            return None
        fast = os.environ.get("BRIGHT_VISION_FAST_MODEL", "").strip()
        if not fast:
            return None
        heavy = os.environ.get("BRIGHT_VISION_HEAVY_MODEL", "").strip() or None
        return cls(
            enabled=True,
            fast_model=fast,
            heavy_model=heavy,
            token_fast_max=int(os.environ.get("BRIGHT_VISION_ROUTER_TOKEN_FAST_MAX", "4096")),
            token_heavy_min=int(os.environ.get("BRIGHT_VISION_ROUTER_TOKEN_HEAVY_MIN", "12000")),
            escalate_on_failure=os.environ.get("BRIGHT_VISION_ROUTER_ESCALATE", "1").strip()
            not in ("0", "false", "no"),
        )


@dataclass
class RouteDecision:
    tier: RouteTier
    model_name: str
    estimated_tokens: int
    reasons: list[str] = field(default_factory=list)


def estimate_prompt_tokens(
    user_message: str,
    *,
    files_in_chat: int = 0,
    message_token_count: int | None = None,
) -> int:
    if message_token_count is not None and message_token_count > 0:
        return message_token_count
    base = max(len(user_message) // 4, 32)
    return base + files_in_chat * 1_500


def classify_prompt(
    user_message: str,
    *,
    estimated_tokens: int,
    router: ModelRouterConfig,
    heavy_model_name: str,
    force_tier: RouteTier | None = None,
) -> RouteDecision:
    if force_tier:
        model = router.fast_model if force_tier == "fast" else heavy_model_name
        return RouteDecision(
            tier=force_tier,
            model_name=model,
            estimated_tokens=estimated_tokens,
            reasons=[f"forced:{force_tier}"],
        )

    reasons: list[str] = []

    if estimated_tokens >= router.token_heavy_min:
        reasons.append(f"tokens>={router.token_heavy_min}")
        return RouteDecision(
            tier="heavy",
            model_name=heavy_model_name,
            estimated_tokens=estimated_tokens,
            reasons=reasons,
        )

    heavy_hit = _HEAVY_PATTERNS.search(user_message)
    fast_hit = _FAST_PATTERNS.search(user_message)

    if heavy_hit:
        reasons.append(f"keyword:{heavy_hit.group(0).lower()}")
        return RouteDecision(
            tier="heavy",
            model_name=heavy_model_name,
            estimated_tokens=estimated_tokens,
            reasons=reasons,
        )

    if fast_hit and estimated_tokens < router.token_heavy_min:
        reasons.append(f"keyword:{fast_hit.group(0).lower()}")

    if estimated_tokens < router.token_fast_max and (fast_hit or not _CODE_TASK.search(user_message)):
        if not fast_hit:
            reasons.append(f"tokens<{router.token_fast_max}")
        return RouteDecision(
            tier="fast",
            model_name=router.fast_model,
            estimated_tokens=estimated_tokens,
            reasons=reasons,
        )

    reasons.append("default_heavy")
    return RouteDecision(
        tier="heavy",
        model_name=heavy_model_name,
        estimated_tokens=estimated_tokens,
        reasons=reasons,
    )


def should_escalate_fast_turn(
    decision: RouteDecision,
    *,
    router: ModelRouterConfig,
    user_message: str,
    edited_files: list[str],
    assistant_text: str,
    had_tool_error: bool = False,
) -> bool:
    if not router.escalate_on_failure or decision.tier != "fast":
        return False
    if edited_files:
        return False
    if had_tool_error:
        return _CODE_TASK.search(user_message) is not None
    if len(assistant_text.strip()) > 400:
        return False
    if not _CODE_TASK.search(user_message):
        return False
    return True
