from __future__ import annotations

import argparse
import os
from contextlib import contextmanager


@contextmanager
def _student_grpc_detection():
    import ansys.aedt.core.desktop as desktop_module
    from ansys.aedt.core.generic.general_methods import active_sessions

    original = desktop_module.is_grpc_session_active

    def detector(port, machine=None):
        if original(port, machine):
            return True
        return port in active_sessions(student_version=True, non_graphical=None).values()

    desktop_module.is_grpc_session_active = detector
    try:
        yield
    finally:
        desktop_module.is_grpc_session_active = original


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, required=True)
    args = parser.parse_args()
    target = os.environ.get("HFSS_AGENT_SCRIPT_TARGET")
    if not target:
        raise RuntimeError("HFSS_AGENT_SCRIPT_TARGET is missing")

    from ansys.aedt.core import Desktop
    from ansys.aedt.core.generic.general_methods import active_sessions

    sessions = active_sessions(student_version=True)
    process_id = next((pid for pid, session_port in sessions.items() if session_port == args.port), None)
    if process_id is None:
        raise RuntimeError(
            "No active Student AEDT process was found on gRPC port " + str(args.port)
        )

    with _student_grpc_detection():
        desktop = Desktop(
            version="2025.2",
            student_version=True,
            machine="localhost",
            port=args.port,
            new_desktop=False,
            aedt_process_id=process_id,
            close_on_exit=False,
            non_graphical=True,
        )
    try:
        desktop.odesktop.RunScript(target)
        print("PyAEDT Student bridge executed: " + target)
        return 0
    finally:
        desktop.release_desktop(False, False)


if __name__ == "__main__":
    raise SystemExit(main())
