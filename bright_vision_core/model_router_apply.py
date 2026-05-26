"""Apply a route decision to a live cecli Coder (swap main_model + Ollama keep_alive)."""

from __future__ import annotations

from cecli import models

from bright_vision_core.model_router import ModelRouterConfig, RouteDecision


def apply_route_to_coder(coder, decision: RouteDecision, router: ModelRouterConfig) -> None:
    """Point the coder at the routed model for this turn."""
    prev = coder.main_model
    new_model = models.Model(decision.model_name, from_model=prev)
    if new_model.is_ollama():
        new_model._ensure_extra_params_dict()
        keep_alive = (
            router.keep_alive_fast if decision.tier == "fast" else router.keep_alive_heavy
        )
        new_model.extra_params["keep_alive"] = keep_alive
    coder.main_model = new_model
