"""
mcp-luopan — MCP server wrapping the Four Pillars of Destiny HTTP backend.

Provides two tools: luopan_analyze (full chart reading) and luopan_chat
(follow-up). Pure HTTP proxy — all domain work happens upstream.

Install:  uv pip install -e /Users/Neil/Projects/mcp-servers/mcp-luopan
Run:      mcp-luopan   (or: python -m mcp_luopan)
"""

from __future__ import annotations

import asyncio
import json
import logging
import sys

try:
    from mcp.server.fastmcp import FastMCP
except ImportError:
    print("Error: pip install mcp[cli]", file=sys.stderr)
    sys.exit(1)

from .client import LuopanClient, LuopanServiceError
from .config import load_config

logging.basicConfig(level=logging.INFO, stream=sys.stderr)
logger = logging.getLogger("luopan")

mcp = FastMCP("luopan")
_config = load_config()
_client = LuopanClient(_config)


def _err(kind: str, hint: str) -> str:
    return json.dumps({"error": kind, "hint": hint}, ensure_ascii=False)


def _dump(payload: dict) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2)


@mcp.tool()
async def luopan_analyze(year: int, month: int, day: int, hour: int, gender: int) -> str:
    """Produce a full destiny-chart reading for a birth moment.

    IMPORTANT: Before calling, you MUST confirm with the user:
      - solar calendar date (阳历): year / month / day
      - birth hour 0-23 (时辰)，if unsure warn them the reading will be less precise
      - gender: 1 for 男, 0 for 女

    Output contains: session_id (used for follow-ups), sizhu (the chart),
    pattern (格局), report (a three-tier reading), dayun (luck pillars),
    highlights (notable traits), partner (气场画像), female (if gender=0),
    and followup_remaining (starts at 5).

    When presenting to the user, translate technical terms (e.g. 十神, 格局名称)
    into plain language like "气场 / 画像 / 此局". The public persona is 罗盘
    (fengshui compass), never expose the words 八字 / 子平.

    Sessions expire in 2 hours and allow up to 5 follow-up questions via luopan_chat.

    Args:
        year: Birth year, e.g. 1991
        month: Birth month 1-12
        day: Birth day 1-31
        hour: Birth hour 0-23
        gender: 1 = 男, 0 = 女
    """
    if not (1900 <= year <= 2100):
        return _err("bad_input", f"年份 {year} 超出支持范围 1900-2100")
    if not (1 <= month <= 12):
        return _err("bad_input", f"月份 {month} 无效")
    if not (1 <= day <= 31):
        return _err("bad_input", f"日期 {day} 无效")
    if not (0 <= hour <= 23):
        return _err("bad_input", f"时辰 {hour} 无效，应为 0-23")
    if gender not in (0, 1):
        return _err("bad_input", f"性别 {gender} 无效，应为 0 (女) 或 1 (男)")

    try:
        data = await _client.analyze(year, month, day, hour, gender)
    except LuopanServiceError as e:
        if e.kind == "service_unreachable":
            return _err("service_unreachable", f"罗盘后端未就绪：{_config.api_base}。请先启动 uvicorn。")
        return _err(e.kind, e.detail)
    except Exception as e:  # noqa: BLE001
        logger.exception("luopan_analyze unexpected error")
        return _err("internal", str(e))

    if isinstance(data, dict) and data.get("session_id"):
        data.setdefault("followup_remaining", 5)
    data["_next_step"] = (
        "向用户概述 report.tier1，抛 2-3 个 highlights 作为切入点，"
        "并保存 session_id 至 memory/sessions.json。追问时调 luopan_chat。"
    )
    return _dump(data)


@mcp.tool()
async def luopan_chat(session_id: str, question: str) -> str:
    """Ask a follow-up question against an existing chart-reading session.

    Session_id comes from a prior luopan_analyze call. The backend enforces
    a 2-hour TTL and a 5-question cap; when either is hit, call luopan_analyze
    again to open a new session.

    Returns (normalized):
      answer:              the AI reply text
      followup_remaining:  questions you still have left after this one
      followup_count:      questions used so far (incl. this one)
      max_followups:       hard cap (5)
      session_id:          echoed back

    When `followup_remaining == 0` or this call returns `session_expired`,
    the next turn must call luopan_analyze to open a fresh session.
    When `followup_remaining == 1`, warn the user before they spend it.

    Args:
        session_id: The session_id returned by luopan_analyze
        question: The user's follow-up question (specific events / years / topics
                  yield better answers than vague "is my fate good")
    """
    if not session_id or len(session_id) > 64:
        return _err("bad_input", "session_id 无效")
    if not question.strip():
        return _err("bad_input", "问题不能为空")

    try:
        data = await _client.chat(session_id, question.strip())
    except LuopanServiceError as e:
        if e.kind == "session_expired":
            return _err("session_expired", "此盘气已散（session 过期或追问已尽），需重新起盘。")
        if e.kind == "service_unreachable":
            return _err("service_unreachable", f"罗盘后端未就绪：{_config.api_base}。请先启动 uvicorn。")
        return _err(e.kind, e.detail)
    except Exception as e:  # noqa: BLE001
        logger.exception("luopan_chat unexpected error")
        return _err("internal", str(e))

    count = data.get("followup_count", 0)
    cap = data.get("max_followups", 5)
    normalized = {
        "answer": data.get("reply", ""),
        "followup_remaining": max(cap - count, 0),
        "followup_count": count,
        "max_followups": cap,
        "session_id": data.get("session_id", session_id),
    }
    return _dump(normalized)


def main():
    logger.info("Starting luopan MCP server (api_base=%s)", _config.api_base)
    mcp.run()


if __name__ == "__main__":
    main()
