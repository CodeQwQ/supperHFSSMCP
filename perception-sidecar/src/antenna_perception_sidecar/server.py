from __future__ import annotations

import base64
import json
import os
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from antenna_perception_sidecar.engine import CompositeEngine, DemoEngine, Engine, load_engine


class ExtractRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    protocol_version: str = Field(pattern="^1$")
    input_digest: str = Field(pattern=r"^[a-f0-9]{64}$")
    input_suffix: str = Field(pattern=r"^\.(pdf|png|jpg|jpeg)$")
    content_base64: str = Field(min_length=1)


def configured_engine() -> Engine:
    specs = [
        os.getenv("PERCEPTION_OCR_ENGINE_MODULE"),
        os.getenv("PERCEPTION_VLM_ENGINE_MODULE"),
    ]
    engines = [load_engine(spec) for spec in specs if spec]
    return CompositeEngine(engines) if engines else DemoEngine()


def create_server(host: str, port: int, engine: Engine) -> ThreadingHTTPServer:
    class Handler(BaseHTTPRequestHandler):
        def _write(self, status: int, payload: dict[str, Any]) -> None:
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self) -> None:  # noqa: N802
            if self.path not in {"/health", "/model-info"}:
                self._write(HTTPStatus.NOT_FOUND, {"success": False, "error": "not_found"})
                return
            self._write(
                HTTPStatus.OK,
                {
                    "success": True,
                    "engine_id": engine.engine_id,
                    "engine_version": engine.engine_version,
                    "capabilities": engine.capabilities,
                },
            )

        def do_POST(self) -> None:  # noqa: N802
            if self.path != "/extract":
                self._write(HTTPStatus.NOT_FOUND, {"success": False, "error": "not_found"})
                return
            try:
                length = int(self.headers.get("Content-Length", "0"))
                request = ExtractRequest.model_validate(json.loads(self.rfile.read(length)))
                content = base64.b64decode(request.content_base64, validate=True)
                records = engine.extract(request.input_digest, request.input_suffix, content)
                self._write(
                    HTTPStatus.OK,
                    {
                        "protocol_version": "1",
                        "provider_id": engine.engine_id,
                        "provider_version": engine.engine_version,
                        "evidence": records,
                    },
                )
            except (ValidationError, ValueError, json.JSONDecodeError) as error:
                self._write(HTTPStatus.BAD_REQUEST, {"success": False, "error": str(error)})

        def log_message(self, *_args: object) -> None:
            return

    return ThreadingHTTPServer((host, port), Handler)


def run() -> None:
    host = os.getenv("PERCEPTION_HOST", "127.0.0.1")
    port = int(os.getenv("PERCEPTION_PORT", "8020"))
    server = create_server(host, port, configured_engine())
    print(f"Perception sidecar listening on http://{host}:{port}", flush=True)
    try:
        server.serve_forever()
    finally:
        server.server_close()
