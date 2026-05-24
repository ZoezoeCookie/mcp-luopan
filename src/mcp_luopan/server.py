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
async def luopan_analyze(
    year: int,
    month: int,
    day: int,
    hour: int,
    gender: int,
    calendar: str = "solar",
    is_leap_month: bool = False,
) -> str:
    """Produce a full destiny-chart reading for a birth moment.

    IMPORTANT: Before calling, you MUST confirm with the user:
      - the birth date (year / month / day)
      - **whether the date is 公历 (solar) or 农历 (lunar)** —— ask explicitly
        if not clear, then pass calendar accordingly
      - birth hour 0-23 (时辰)，if unsure warn them the reading will be less precise
      - gender: 1 for 男, 0 for 女

    Output contains: session_id (used for follow-ups), sizhu (the chart),
    pattern (格局), report (a three-tier reading), dayun (luck pillars),
    highlights (notable traits), partner (气场画像), female (if gender=0).

    Output style (人设, 措辞) is owned by the agent's SOUL / skills, not by
    this tool. Professional terms (十神, 格局名, 大运, 流年, 财星, 印星 …) may
    be used directly without translation.

    Sessions expire in 2 hours. Follow-ups are unlimited until the session
    expires; on expiry call luopan_analyze again to open a fresh session.

    Args:
        year: Birth year, e.g. 1991
        month: Birth month 1-12
        day: Birth day 1-31
        hour: Birth hour 0-23
        gender: 1 = 男, 0 = 女
        calendar: 'solar' (公历, default) or 'lunar' (农历). If the user gave
          a 农历 date, **you MUST pass calendar='lunar'**. Do NOT mentally
          convert and pretend the date is solar — this tool + backend do the
          conversion (via lunar-python) and will return an audit trail
          (`input.solar` shows the converted result; `input.calendar_input`
          echoes what you passed). Lying about having converted is a
          known failure mode that produces wrong charts.
        is_leap_month: ONLY relevant when calendar='lunar' AND the user's
          birth month is a 闰月. E.g. 2020 有闰四月 → 闰四月初一: pass
          year=2020, month=4, day=1, is_leap_month=True. If you are unsure
          whether the month is leap, leave this False (default) — passing
          True for a non-leap month will return bad_input.
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
    if calendar not in ("solar", "lunar"):
        return _err("bad_input", f"calendar 必须为 'solar' 或 'lunar'，收到 {calendar!r}")

    try:
        data = await _client.analyze(year, month, day, hour, gender, calendar, is_leap_month)
    except LuopanServiceError as e:
        if e.kind == "service_unreachable":
            return _err("service_unreachable", f"罗盘后端未就绪：{_config.api_base}。请先启动 uvicorn。")
        return _err(e.kind, e.detail)
    except Exception as e:  # noqa: BLE001
        logger.exception("luopan_analyze unexpected error")
        return _err("internal", str(e))

    data["_next_step"] = (
        "向用户概述 report.tier1，抛 2-3 个 highlights 作为切入点，"
        "并保存 session_id 至 memory/sessions.json。追问时调 luopan_chat。"
    )
    return _dump(data)


@mcp.tool()
async def luopan_chat(session_id: str, question: str) -> str:
    """Ask a follow-up question against an existing chart-reading session.

    Session_id comes from a prior luopan_analyze call. The backend enforces
    a 2-hour TTL only; follow-ups are unlimited within that window. On
    session_expired, call luopan_analyze again to open a fresh session.

    Returns:
      answer:              the AI reply text
      followup_count:      questions used so far in this session (incl. this one)
      session_id:          echoed back

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
            return _err("session_expired", "此盘气已散（session 过期），需重新起盘。")
        if e.kind == "service_unreachable":
            return _err("service_unreachable", f"罗盘后端未就绪：{_config.api_base}。请先启动 uvicorn。")
        return _err(e.kind, e.detail)
    except Exception as e:  # noqa: BLE001
        logger.exception("luopan_chat unexpected error")
        return _err("internal", str(e))

    normalized = {
        "answer": data.get("reply", ""),
        "followup_count": data.get("followup_count", 0),
        "session_id": data.get("session_id", session_id),
    }
    return _dump(normalized)


def main():
    logger.info("Starting luopan MCP server (api_base=%s)", _config.api_base)
    mcp.run()


if __name__ == "__main__":
    main()
