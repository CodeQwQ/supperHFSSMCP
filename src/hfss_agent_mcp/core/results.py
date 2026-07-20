from __future__ import annotations

from math import isfinite, pow
from typing import Any, Iterable


def analyze_s_parameter_points(
    sample_points: Iterable[dict[str, Any]],
    *,
    target_frequency_ghz: float | None = None,
    threshold_db: float = -10.0,
) -> dict[str, Any]:
    """Calculate useful one-port S-parameter metrics from frequency samples."""
    points = _normalise_points(sample_points)
    if not points:
        raise ValueError("At least one S-parameter sample point is required.")

    minimum_index = min(range(len(points)), key=lambda index: points[index]["value_db"])
    minimum = points[minimum_index]
    passing_indices = [
        index for index, point in enumerate(points) if point["value_db"] <= threshold_db
    ]
    bandwidth = _bandwidth_around_minimum(points, minimum_index, passing_indices, threshold_db)
    reflection = pow(10.0, minimum["value_db"] / 20.0)
    vswr = (1.0 + reflection) / (1.0 - reflection) if reflection < 1.0 else float("inf")

    target: dict[str, Any] | None = None
    if target_frequency_ghz is not None:
        target_point = min(
            points,
            key=lambda point: abs(point["frequency_ghz"] - target_frequency_ghz),
        )
        target = {
            "frequency_ghz": target_frequency_ghz,
            "nearest_sample_frequency_ghz": target_point["frequency_ghz"],
            "value_db": target_point["value_db"],
            "threshold_db": threshold_db,
            "passed": target_point["value_db"] <= threshold_db,
        }

    result = {
        "sample_count": len(points),
        "threshold_db": threshold_db,
        "resonance_frequency_ghz": minimum["frequency_ghz"],
        "minimum_value_db": minimum["value_db"],
        "bandwidth_ghz": bandwidth["bandwidth_ghz"],
        "bandwidth_percent": bandwidth["bandwidth_percent"],
        "band_edges_ghz": bandwidth["band_edges_ghz"],
        "vswr_at_resonance": vswr,
        "target": target,
        "sample_points": points,
    }
    return result


def analyze_input_impedance(
    sample_points: Iterable[dict[str, Any]],
    *,
    target_frequency_ghz: float | None = None,
) -> dict[str, Any]:
    """Summarise complex input impedance samples returned by AEDT."""
    points = []
    for raw in sample_points:
        frequency = _finite_number(raw.get("frequency_ghz"), "frequency_ghz")
        real = _finite_number(raw.get("real_ohms", raw.get("real")), "real_ohms")
        imag = _finite_number(raw.get("imag_ohms", raw.get("imag")), "imag_ohms")
        points.append(
            {
                "frequency_ghz": frequency,
                "real_ohms": real,
                "imag_ohms": imag,
                "magnitude_ohms": (real * real + imag * imag) ** 0.5,
            }
        )
    points.sort(key=lambda point: point["frequency_ghz"])
    if not points:
        raise ValueError("At least one impedance sample point is required.")

    target = None
    if target_frequency_ghz is not None:
        nearest = min(points, key=lambda point: abs(point["frequency_ghz"] - target_frequency_ghz))
        target = {
            "frequency_ghz": target_frequency_ghz,
            "nearest_sample_frequency_ghz": nearest["frequency_ghz"],
            "real_ohms": nearest["real_ohms"],
            "imag_ohms": nearest["imag_ohms"],
            "magnitude_ohms": nearest["magnitude_ohms"],
        }
    return {"sample_count": len(points), "target": target, "sample_points": points}


def _normalise_points(sample_points: Iterable[dict[str, Any]]) -> list[dict[str, float]]:
    points = [
        {
            "frequency_ghz": _finite_number(point.get("frequency_ghz"), "frequency_ghz"),
            "value_db": _finite_number(point.get("value_db"), "value_db"),
        }
        for point in sample_points
    ]
    points.sort(key=lambda point: point["frequency_ghz"])
    return points


def _bandwidth_around_minimum(
    points: list[dict[str, float]],
    minimum_index: int,
    passing_indices: list[int],
    threshold_db: float,
) -> dict[str, Any]:
    if not passing_indices or minimum_index not in passing_indices:
        return {"bandwidth_ghz": 0.0, "bandwidth_percent": 0.0, "band_edges_ghz": None}

    left = minimum_index
    while left - 1 in passing_indices:
        left -= 1
    right = minimum_index
    while right + 1 in passing_indices:
        right += 1

    lower = points[left]["frequency_ghz"]
    if left > 0:
        lower = _crossing_frequency(points[left - 1], points[left], threshold_db)
    upper = points[right]["frequency_ghz"]
    if right + 1 < len(points):
        upper = _crossing_frequency(points[right], points[right + 1], threshold_db)

    bandwidth = max(0.0, upper - lower)
    center = (upper + lower) / 2.0
    percent = bandwidth / center * 100.0 if center else 0.0
    return {
        "bandwidth_ghz": bandwidth,
        "bandwidth_percent": percent,
        "band_edges_ghz": {"lower": lower, "upper": upper},
    }


def _crossing_frequency(
    first: dict[str, float],
    second: dict[str, float],
    threshold_db: float,
) -> float:
    denominator = second["value_db"] - first["value_db"]
    if denominator == 0:
        return first["frequency_ghz"]
    fraction = (threshold_db - first["value_db"]) / denominator
    fraction = min(1.0, max(0.0, fraction))
    return first["frequency_ghz"] + fraction * (
        second["frequency_ghz"] - first["frequency_ghz"]
    )


def _finite_number(value: Any, field_name: str) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field_name} must be numeric.") from exc
    if not isfinite(number):
        raise ValueError(f"{field_name} must be finite.")
    return number
