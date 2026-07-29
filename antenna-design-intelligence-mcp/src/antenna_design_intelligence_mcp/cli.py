from __future__ import annotations

import argparse
import asyncio
from dataclasses import replace
from typing import Sequence

from antenna_design_intelligence_mcp.config import ServerConfig
from antenna_design_intelligence_mcp.server import create_app


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="antenna-design-intelligence-mcp",
        description="运行或检查天线设计信息理解 MCP 服务。",
    )
    subparsers = parser.add_subparsers(dest="command")
    run_parser = subparsers.add_parser("run", help="运行 MCP 服务。")
    _add_common_options(run_parser)
    list_parser = subparsers.add_parser("list-tools", help="列出 MCP tools。")
    _add_common_options(list_parser)
    return parser


def _add_common_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--transport", choices=["stdio", "sse", "streamable-http"])
    parser.add_argument("--host")
    parser.add_argument("--port", type=int)


def _config_from_args(args: argparse.Namespace) -> ServerConfig:
    config = ServerConfig.from_env()
    updates = {
        key: value
        for key, value in {
            "transport": args.transport,
            "host": args.host,
            "port": args.port,
        }.items()
        if value is not None
    }
    return replace(config, **updates)


async def _list_tools(config: ServerConfig) -> int:
    app = create_app(config)
    for tool in await app.list_tools():
        print(tool.name)
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command is None:
        args.command = "run"
        args.transport = args.host = None
        args.port = None
    config = _config_from_args(args)
    if args.command == "list-tools":
        return asyncio.run(_list_tools(config))
    create_app(config).run(transport=config.transport)
    return 0
