from __future__ import annotations

from dataclasses import asdict

from hfss_agent_mcp.core.models import SetupSpec, SweepSpec


def setup_to_dict(spec: SetupSpec) -> dict[str, object]:
    data = asdict(spec)
    data["adaptive"] = {
        "max_delta_s": spec.max_delta_s,
        "max_passes": spec.max_passes,
        "min_passes": spec.min_passes,
    }
    return data


def sweep_to_dict(spec: SweepSpec) -> dict[str, object]:
    return asdict(spec)
