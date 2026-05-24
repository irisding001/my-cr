import json
import logging
import threading
import time
import anthropic
from json_repair import repair_json
from config import VIOLATION_RULES, ANTHROPIC_API_KEY, ANTHROPIC_MODEL

logger = logging.getLogger(__name__)

_client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY, max_retries=3)

# Rate limiter: max 25 requests per 60 seconds
_rate_lock = threading.Lock()
_request_times: list[float] = []
_RATE_LIMIT = 25


def _wait_for_rate_limit():
    with _rate_lock:
        now = time.time()
        _request_times[:] = [t for t in _request_times if now - t < 60]
        if len(_request_times) >= _RATE_LIMIT:
            sleep_time = 60 - (now - _request_times[0]) + 0.5
            if sleep_time > 0:
                time.sleep(sleep_time)
        _request_times.append(time.time())

SYSTEM_PROMPT = f"""你是 moomoo MY 金融服务的专业客服质检员，负责审查 WhatsApp 客服对话记录。

对话语言可能为中文、英文或马来文的混合，你都能理解并准确质检。

{VIOLATION_RULES}

请严格按照以上违规规则进行判断，输出标准 JSON 格式的质检报告，不要输出任何其他内容。"""

QC_PROMPT = """请对以下客服对话进行全面质检分析。

## 对话信息
- 客服名称：{agent_name}
- 客户ID：{customer_id}
- 日期：{date}
{response_time_note}

## 对话记录
{conversation_text}

## 质检维度
1. **合规违禁**：根据系统提示中的 A/B/C 三级违规规则，列出所有发现的违规（可多条）
2. **服务态度**：1-5分，识别不礼貌、敷衍、冷漠、强制沟通等问题
3. **问题解决率与回答正确性**：问题是否被解决，回答是否准确
4. **投诉风险**：高/中/低，识别潜在投诉风险点

注意：
- C3/B6（超时未回复）已由系统预先计算并标注在"对话信息"中，请直接引用
- B4/C1：注意识别客服是否在未解答的情况下直接让客户联系其他部门
- B5/C2：注意识别客服是否做出了无法确认已履行的承诺
- B7/C6：注意识别过度推销、强制沟通、忽视客户拒绝等行为

**重要判断原则（避免误判）：**
- 客服发出消息后客户未回复，属于正常结果，**不算任何违规，也不需要跟进**；如果对话仅包含客服主动外发（如推广、问候）且客户未回应，`action_required` 应为 false，`complaint_risk` 应为低
- **A1 的判断标准极为严格**：必须有明确的"领奖后提现"引导（如客服说"存款领奖后你可以马上提走"或"领完再取出来就行"），才算 A1；以下情形**绝对不是 A1**：
  - 发送活动介绍、奖励档位说明（如 RM1,000→RM100 cash）
  - 提醒客户在截止日期前领取奖励（如"31/5 前务必领取"）
  - 附上活动链接或 T&C 链接
  - 引导客户存款以获得欢迎奖励——这是正常销售推广
- 对话记录中消息顺序偶有混乱（如客服消息出现在客户 ID 下）可能是系统展示问题，**不应直接认定为弄虚作假**，除非有其他实质证据

只输出 JSON，不要任何其他内容：
{{
  "agent_name": "客服名称",
  "customer_id": "客户ID",
  "date": "日期",
  "violations": [
    {{
      "level": "A级/B级/C级",
      "code": "A1/A2/A3/B1/B2/B3/B4/B5/B6/B7/C1/C2/C3/C4/C5/C6",
      "description": "违规行为简述",
      "evidence": "对话中的具体证据原文"
    }}
  ],
  "attitude_score": 4,
  "attitude_issues": "具体问题，无问题填 null",
  "resolution_status": "已解决/部分解决/未解决",
  "resolution_detail": "具体说明",
  "accuracy": "准确/有误/无法判断",
  "accuracy_issues": "具体错误内容，准确则填 null",
  "complaint_risk": "高/中/低",
  "complaint_risk_reason": "风险原因，无风险填 null",
  "complaint_signal": "客户原话（如 'I will make a complaint'），无则填 null",
  "summary": "2-3句整体质检摘要",
  "action_required": true,
  "action_detail": "需跟进的具体事项，无需跟进填 null"
}}"""


def format_conversation(messages: list[dict]) -> str:
    lines = []
    for m in messages:
        role_label = f"【{m.get('sender', '客服' if m['role'] == 'agent' else '客户')}】"
        time_label = f" ({m['timestamp']})" if m.get("timestamp") else ""
        lines.append(f"{role_label}{time_label}: {m['content']}")
    return "\n".join(lines)


def analyze_conversation(conversation: dict) -> dict:
    conversation_text = format_conversation(conversation["messages"])

    rt_flags = conversation.get("response_time_flags", [])
    if rt_flags:
        notes = "\n".join(f"- ⚠️ {f}" for f in rt_flags)
        response_time_note = f"\n## 系统预检（回复超时）\n{notes}"
    else:
        response_time_note = ""

    prompt = QC_PROMPT.format(
        agent_name=conversation.get("agent_name", "Unknown"),
        customer_id=conversation.get("customer_id", "Unknown"),
        date=conversation.get("date", ""),
        response_time_note=response_time_note,
        conversation_text=conversation_text,
    )

    _wait_for_rate_limit()
    msg = _client.messages.create(
        model=ANTHROPIC_MODEL,
        max_tokens=2048,
        temperature=0.1,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": prompt}],
    )
    raw = msg.content[0].text.strip()

    # Extract JSON: find outermost { ... }
    start = raw.find("{")
    end = raw.rfind("}")
    if start != -1 and end != -1 and end > start:
        raw = raw[start:end + 1]

    try:
        result = json.loads(raw)
    except json.JSONDecodeError:
        result = json.loads(repair_json(raw))
    result["raw_conversation"] = conversation_text

    # Merge pre-calculated response time violations if Claude missed them
    if rt_flags and not any(v.get("code") in ("C3", "B6") for v in result.get("violations", [])):
        for flag in rt_flags:
            level = "B级" if "8小时" in flag else "C级"
            code = "B6" if "8小时" in flag else "C3"
            result.setdefault("violations", []).append({
                "level": level,
                "code": code,
                "description": flag,
                "evidence": "系统计算",
            })

    return result
