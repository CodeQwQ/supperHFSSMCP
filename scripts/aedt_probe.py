import json
import io
import os


def _name(value):
    if value is None:
        return None
    for attribute in ("GetName", "project_name", "design_name", "name"):
        candidate = getattr(value, attribute, None)
        if callable(candidate):
            try:
                return candidate()
            except Exception:
                continue
        if candidate is not None:
            return str(candidate)
    return None


def _probe_desktop(desktop):
    project = None
    project_getter = getattr(desktop, "GetActiveProject", None)
    if callable(project_getter):
        project = project_getter()
    if project is None:
        project = getattr(desktop, "active_project", None)
    design = None
    if project is not None:
        design_getter = getattr(project, "GetActiveDesign", None)
        if callable(design_getter):
            design = design_getter()
        if design is None:
            design = getattr(project, "active_design", None)
    return {"project_name": _name(project), "design_name": _name(design)}


def _context():
    context_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".hfss-agent-context.json")
    try:
        with io.open(context_path, "r", encoding="utf-8") as context_file:
            return json.load(context_file)
    except Exception:
        return {}


desktop_object = globals().get("desktop")
if desktop_object is None:
    desktop_object = globals().get("oDesktop")
context = _context()
arguments = context.get("arguments", {})
try:
    arguments = json.loads(os.environ.get("HFSS_AGENT_SCRIPT_ARGS", ""))
except Exception:
    if not arguments:
        arguments = {"_raw": os.environ.get("HFSS_AGENT_SCRIPT_ARGS", "")}
payload = {
    "script_id": os.environ.get("HFSS_AGENT_SCRIPT_ID") or context.get("script_id"),
    "arguments": arguments,
    "success": desktop_object is not None,
}
if desktop_object is not None:
    payload.update(_probe_desktop(desktop_object))
output_path = os.environ.get("HFSS_AGENT_SCRIPT_OUTPUT") or context.get("output")
if output_path:
    with io.open(output_path, "w", encoding="utf-8") as output_file:
        json.dump(payload, output_file, ensure_ascii=True)
print(json.dumps(payload, ensure_ascii=True))
