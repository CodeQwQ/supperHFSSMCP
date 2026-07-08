from __future__ import annotations

import argparse
import asyncio
from dataclasses import replace
from typing import Sequence

from hfss_agent_mcp.config import ServerConfig
from hfss_agent_mcp.server import create_app


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="hfss-agent-mcp",
        description="Run or inspect the HFSS Agent MCP server.",
    )
    subparsers = parser.add_subparsers(dest="command")

    run_parser = subparsers.add_parser("run", help="Run the MCP server.")
    _add_common_options(run_parser)

    list_parser = subparsers.add_parser("list-tools", help="Print registered MCP tool names.")
    _add_common_options(list_parser)

    return parser


def _add_common_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--backend", choices=["mock", "pyaedt"], default=None)
    parser.add_argument(
        "--transport",
        choices=["stdio", "sse", "streamable-http"],
        default=None,
        help="MCP transport. Use streamable-http for a shared server endpoint.",
    )
    parser.add_argument("--host", default=None)
    parser.add_argument("--port", type=int, default=None)
    parser.add_argument("--log-level", default=None)


def _config_from_args(args: argparse.Namespace) -> ServerConfig:
    config = ServerConfig.from_env()
    updates = {
        key: value
        for key, value in {
            "backend": args.backend,
            "transport": args.transport,
            "host": args.host,
            "port": args.port,
            "log_level": args.log_level,
        }.items()
        if value is not None
    }
    return replace(config, **updates)


async def _list_tools(config: ServerConfig) -> int:
    app = create_app(config)
    tools = await app.list_tools()
    for tool in tools:
        print(tool.name)
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command is None:
        args.command = "run"
        args.backend = None
        args.transport = None
        args.host = None
        args.port = None
        args.log_level = None

    config = _config_from_args(args)

    if args.command == "list-tools":
        return asyncio.run(_list_tools(config))

    app = create_app(config)
    app.run(transport=config.transport)
    return 0
