# mcp-luopan

把"罗盘"——基于子平真诠格局法的命盘推算——做成一个 MCP（Model Context Protocol）工具集，让任何 MCP 客户端（Claude Code / Claude Desktop / OpenClaw / Cursor / 自研 LLM Agent）都能在对话里给用户起盘、读盘、追问。

云端入口已上线：[https://luopan.caihangao.com](https://luopan.caihangao.com)。MCP 默认就指向它，开箱即用，**不需要本机起服务**。

---

## 它解决什么问题

LLM 自己**不会**算八字。让模型直接基于训练知识"分析命盘"是错的——干支、月令、十神、格局判定全是规则计算，必须由专门的引擎做。

mcp-luopan 把整套引擎（排盘 → 十神 → 格局 → 大运 → 报告 → 多轮追问）封装成 3 个 MCP 工具，LLM 不再瞎编，而是：

1. **拿到准确的命盘数据**（四柱 / 格局 / 大运 / 五行 / 十神）
2. **依据真实数据组织语言**（讲故事的能力交给 LLM，事实交给引擎）
3. **支持有上下文的追问**（5 次追问 / 2 小时 TTL，由后端 session 管理）

---

## 典型使用场景

### 场景 A：在 Claude Code / Claude Desktop 里给朋友测一个

你（用户）：

> 帮我分析一下 1991 年 3 月 15 日早上 5 点出生的男生，看看格局和今年事业。

Claude 自动：

1. 调 `luopan_analyze(year=1991, month=3, day=15, hour=5, gender=1)` → 拿到 `session_id` 和完整命盘
2. 用自然语言把"正官格 / 天成 / 大运走势 / 配偶画像"翻译给你
3. 你追问"今年事业"→ Claude 调 `luopan_chat(session_id, "今年事业")` → 拿到针对**这一个盘**的回答

整个过程你不需要懂术语、不需要看到 JSON。

### 场景 B：批量分析

你想跑一份"100 个名人的格局分布"：

```python
# 伪代码：让一个 Agent 循环调用
for person in people:
    chart = call_tool("luopan_analyze", **person.birth_info)
    record(person.name, chart["pattern"]["final_pattern"])
```

引擎在云端，不占你本机 CPU；脚本只管 IO 编排。

### 场景 C：嵌入到 OpenClaw / 飞书 Agent

把 `luopan` 注册到 OpenClaw 的 `mcp.json`，给某个 agent（比如飞书 bot）授权这 3 个工具，agent 就能在飞书对话里给用户测命盘 + 追问。当前本机 OpenClaw 已经按这个模式跑过；云端 OpenClaw 部署还在 TODO。

### 场景 D：LLM Eval / 提示工程实验

想测试不同模型解读命盘的语言风格、想给某个 agent 调"罗盘人设"——后端永远返回同一份事实数据，模型差异完全暴露在自然语言层。

---

## Quick start：60 秒上手

### 1. 装

```bash
git clone <this-repo> /Users/Neil/Projects/mcp-servers/mcp-luopan
cd /Users/Neil/Projects/mcp-servers/mcp-luopan
uv venv && uv pip install -e .
```

或用普通 venv：

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e .
```

装好后会有 `mcp-luopan` 可执行（在 `.venv/bin/` 里）。

### 2. 烟雾测试（不进 MCP host 直接验证）

```bash
echo '{"jsonrpc":"2.0","id":1,"method":"tools/list"}' | .venv/bin/mcp-luopan
```

预期看到 3 个工具：`luopan_analyze` / `luopan_chat` / `luopan_session_info`。

### 3. 注册到一个 MCP host

#### Claude Code（当前最常见）

编辑 `~/.claude.json` 或项目级 `.mcp.json`：

```json
{
  "mcpServers": {
    "luopan": {
      "command": "/Users/Neil/Projects/mcp-servers/mcp-luopan/.venv/bin/mcp-luopan",
      "env": {
        "LUOPAN_API_BASE": "https://luopan.caihangao.com",
        "LUOPAN_TIMEOUT_SECONDS": "60"
      }
    }
  }
}
```

重启 Claude Code，然后开一个新会话直接说"用罗盘帮我看个盘"，它就会调工具。

#### OpenClaw（本机或云端）

加到 `~/.openclaw/mcp.json`：

```json
"luopan": {
  "command": "/Users/Neil/Projects/mcp-servers/mcp-luopan/.venv/bin/mcp-luopan",
  "env": {
    "LUOPAN_API_BASE": "https://luopan.caihangao.com",
    "LUOPAN_TIMEOUT_SECONDS": "60"
  }
}
```

要让某个 agent 用它，agent 的 `tools.allow` 不需要显式列 `luopan_*`——OpenClaw 默认让所有 agent 看到 mcp.json 里所有 server。

#### Claude Desktop

编辑 `~/Library/Application Support/Claude/claude_desktop_config.json`，结构同上。

---

## 三个工具的语义

> 所有工具都返回 JSON 字符串。出错时返回 `{"error": "...", "hint": "..."}`，不抛异常给 LLM。

### `luopan_analyze(year, month, day, hour, gender)`

完整命盘分析——一次调用产出全部信息。**调用前必须**：和用户确认阳历日期、出生小时（0-23）、性别（1=男 / 0=女）。

返回字段（节选）：

| 字段 | 内容 |
|---|---|
| `session_id` | 12 位短 ID，用于后续 `luopan_chat` |
| `sizhu` | 四柱（年/月/日/时柱的天干地支） |
| `pattern` | 格局判定（如"正官格 / 天成 / followup_remaining=5"） |
| `report` | 三层解读（卡片 tier1 / 详读 tier2 / 技术 tier3） |
| `dayun` | 大运时间轴 + 5 级吉凶 |
| `highlights` | 命盘亮点（13 条规则，rarity 1-3） |
| `partner` | 互补搭档画像（38 子格局 × 3 状态映射） |
| `female` | 女命专属（夫星/子星/夫妻宫，仅 gender=0 时） |
| `wuxing` / `shishen` | 五行统计 / 十神关系 |
| `followup_remaining` | 还能追问几次（默认 5） |

### `luopan_chat(session_id, question)`

针对某一个已有命盘追问。必须在 2 小时内、5 次以内。

返回（已规范化）：

```json
{
  "answer": "AI 的回答文本",
  "followup_remaining": 4,
  "followup_count": 1,
  "max_followups": 5,
  "session_id": "..."
}
```

`followup_remaining == 0` 或返回 `session_expired` 时，必须重新 `luopan_analyze` 起新盘。

### `luopan_session_info(session_id)`

乐观查 session 状态——**不打后端**。后端没有独立的 session 状态接口，权威判定要靠 `luopan_chat` 的报错。这个工具是为 agent 在本地维护"记得 session 是否过期"的辅助。

---

## 配置参数

| 环境变量 | 默认值 | 说明 |
|---|---|---|
| `LUOPAN_API_BASE` | `http://127.0.0.1:8000` | 后端地址。云端推荐 `https://luopan.caihangao.com`；本机调试用 `http://127.0.0.1:8000` 起 uvicorn |
| `LUOPAN_TIMEOUT_SECONDS` | `60` | HTTP 超时。AI 分析偶尔 30s+，留够余量 |
| `LUOPAN_HTTP_RETRIES` | `1` | 短暂网络抖动重试次数 |

---

## 一段完整 LLM 对话示例

下面是 LLM 应该自动产生的工具调用序列（你只需要正常对话）：

```
[user] 我哥 1985 年 8 月 12 日中午 12 点出生，男的，最近老换工作，帮我看看是不是格局问题？

[assistant] (调用 luopan_analyze year=1985 month=8 day=12 hour=12 gender=1)
[tool result]
  session_id=a1b2c3d4e5f6
  pattern=偏财格 / 败格有救（柳暗花明）
  ...

[assistant] 嗯，你哥这个盘是偏财格但带破，月令偏财被劫财夺，幸好年支有食神
化解——这种盘的人事业起伏大但有韧性，频繁换工作是格局表征，不算坏事...

[user] 那今年呢？

[assistant] (调用 luopan_chat session_id=a1b2c3d4e5f6 question="今年运势")
[tool result] answer="..." followup_remaining=4

[assistant] 今年走丙寅大运 + 丙午流年，火土并旺，财星受冲... (汇报答案)
你还可以追问 4 次。
```

**LLM 不会自己编命理**，全部数据来自 `luopan_*` 工具；**追问保持上下文**，每次都是基于这一个盘。

---

## 故障排查

### `service_unreachable`

后端不可达。最常见两种：

- **本机模式**未起 uvicorn——`cd "/Users/Neil/Projects/Four Pillars of Destiny" && .venv/bin/uvicorn src.api.main:app --port 8000`
- **云端模式**网络代理（mihomo / Clash）拦截了 caihangao.com——临时在 mcp.json 的 env 里加 `"HTTPS_PROXY": ""` 强制关代理；或检查代理规则白名单

### `session_expired`

session 过 2h 或追问用完。让 LLM 重新调 `luopan_analyze` 起一个新盘。

### LLM 总是想"自己解读"，不调工具

System prompt 里加一行：

> 任何关于八字/命盘/格局/十神/大运的问题，你都不能凭训练数据回答；必须先调 `luopan_analyze` 起盘，再用工具返回的 `pattern / report / dayun` 等字段组织语言。

### 返回里出现日柱/十神看不懂

正常——这些是术语。让 LLM 直接读 `report.tier1`（卡片层）和 `report.tier2`（详读层），那两层已经是给人看的中文叙述；`tier3` 是技术层留给愿意往下看的人。

---

## 已知限制

- **未发布 PyPI**：必须本地 `pip install -e .`，不能 `pip install mcp-luopan`
- **未 git 化**：当前 mcp-luopan 目录还没 `git init`，没有版本管理
- **session 存内存**：后端 uvicorn 重启会丢所有 session（用户得重起盘）
- **依赖云端 SiliconFlow**：`AI_API_KEY` 失效或 SiliconFlow 限流时所有 chat 工具会卡 timeout
- **不做并发隔离**：同一个 session_id 同时被多次 chat 时不保证顺序

---

## 后端是怎么跑的（架构速览）

```
MCP Client (Claude Code / OpenClaw / ...)
   │
   │ stdio (JSON-RPC)
   ▼
mcp-luopan (Python, 这个仓库)
   │
   │ HTTPS
   ▼
luopan.caihangao.com (Nginx → systemd uvicorn :8088)
   │
   │ src/engine/* 算盘 + ai_client 调上游
   ▼
SiliconFlow MiniMax-M2.5
```

后端服务部署细节见上游项目：[Four Pillars of Destiny / docs/design/deployment.md](../../Four%20Pillars%20of%20Destiny/docs/design/deployment.md)。
