from __future__ import annotations

from math import inf
from typing import Any, Callable, Iterable

from hfss_agent_mcp.core.errors import InputValidationError
from hfss_agent_mcp.core.results import analyze_s_parameter_points


def evaluate_candidate(
    value: Any,
    raw_result: dict[str, Any],
    *,
    target_frequency_ghz: float,
    threshold_db: float = -10.0,
) -> dict[str, Any]:
    try:
        analysis = analyze_s_parameter_points(
            raw_result.get("sample_points", []),
            target_frequency_ghz=target_frequency_ghz,
            threshold_db=threshold_db,
        )
    except (AttributeError, TypeError, ValueError) as exc:
        return {"value": str(value), "status": "failed", "score": inf, "error": str(exc)}
    target = analysis["target"] or {}
    frequency_error = abs(analysis["resonance_frequency_ghz"] - target_frequency_ghz)
    depth_penalty = max(0.0, analysis["minimum_value_db"] - threshold_db)
    return {
        "value": str(value),
        "status": "completed",
        "score": round(frequency_error + depth_penalty, 6),
        "passed": bool(target.get("passed")),
        "analysis": analysis,
    }


def optimize_candidates(
    candidates: Iterable[Any],
    evaluator: Callable[[Any], dict[str, Any]],
    *,
    max_evaluations: int | None = None,
) -> dict[str, Any]:
    values = list(candidates)
    if not values:
        raise InputValidationError("At least one optimization candidate is required.")
    limit = len(values) if max_evaluations is None else max_evaluations
    if limit < 1:
        raise InputValidationError("max_evaluations must be at least 1.")
    evaluations: list[dict[str, Any]] = []
    for value in values[:limit]:
        try:
            result = dict(evaluator(value))
        except Exception as exc:  # Keep the closed loop auditable per candidate.
            result = {"value": str(value), "status": "failed", "score": inf, "error": str(exc)}
        result.setdefault("value", str(value))
        result.setdefault("status", "completed")
        evaluations.append(result)
    completed = [item for item in evaluations if item.get("status") == "completed"]
    if not completed:
        return {
            "status": "failed",
            "best": None,
            "evaluations": evaluations,
            "evaluation_count": len(evaluations),
            "stopped_reason": "all_candidates_failed",
        }
    best = min(completed, key=lambda item: float(item.get("score", inf)))
    stopped_reason = "max_evaluations" if limit < len(values) else "candidate_list_exhausted"
    return {
        "best": best,
        "evaluations": evaluations,
        "evaluation_count": len(evaluations),
        "stopped_reason": stopped_reason,
    }
