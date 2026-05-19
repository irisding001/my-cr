import logging
import re
from datetime import datetime, timedelta
import requests

logger = logging.getLogger(__name__)

BASE_URL = "https://mycm.futuoa.com"


def _parse_cookies(cookie_str: str) -> dict:
    cookies = {}
    for part in cookie_str.strip().split(";"):
        part = part.strip()
        if "=" in part:
            k, v = part.split("=", 1)
            cookies[k.strip()] = v.strip()
    return cookies


class APIClient:
    def __init__(self, cookie_str: str):
        self.cookies = _parse_cookies(cookie_str)
        self.csrf = self.cookies.get("csrfToken", "")
        self.session = requests.Session()
        self.session.cookies.update(self.cookies)
        self.session.headers.update({
            "x-csrf-token": self.csrf,
            "Content-Type": "application/json",
            "Referer": f"{BASE_URL}/customer-mgmt/list",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        })

    def get_customer_list(self, date_str: str) -> list[dict]:
        """Return all customers with WhatsApp activity on date_str (YYYYMMDD)."""
        all_customers = []
        page = 1
        while True:
            payload = {
                "page": page,
                "pageSize": 50,
                "listType": 1,
                "isAdmin": 1,
                "role": 1,
                "waIsWindow": 1,
                "waLastStartTime": date_str,
                "waLastEndTime": date_str,
            }
            resp = self.session.post(
                f"{BASE_URL}/api/am/my/customer/list-v2",
                json=payload,
                timeout=30,
            )
            resp.raise_for_status()
            data = resp.json()

            # Log raw structure on first page so we can verify field names
            if page == 1:
                logger.debug("list-v2 response keys: %s", list(data.keys()))

            records = self._extract_list(data)
            if not records:
                break
            all_customers.extend(records)

            total = self._extract_total(data)
            if total and len(all_customers) >= total:
                break
            if len(records) < 50:
                break
            page += 1

        logger.info("客户列表：共 %d 条", len(all_customers))
        return all_customers

    def get_whatsapp_messages(self, uid: str) -> list[dict]:
        """Return all WhatsApp messages for a customer uid."""
        all_msgs = []
        page = 1
        while True:
            params = {
                "keyword": "",
                "uid": uid,
                "page": page,
                "page_size": 100,
                "channel_type": "whatsapp",
                "search_all": 2,
            }
            resp = self.session.get(
                f"{BASE_URL}/api/whatsapp/message/user-search-list",
                params=params,
                timeout=30,
            )
            resp.raise_for_status()
            data = resp.json()

            if page == 1:
                logger.debug("whatsapp messages response keys: %s", list(data.keys()))

            msgs = self._extract_list(data)
            if not msgs:
                break
            all_msgs.extend(msgs)
            if len(msgs) < 100:
                break
            page += 1

        return all_msgs

    # --- helpers to handle common response envelope patterns ---

    def _extract_list(self, data: dict) -> list:
        """Try common envelope patterns: data.list / data.records / data / list."""
        for path in [
            lambda d: d["data"]["list"],
            lambda d: d["data"]["records"],
            lambda d: d["data"]["items"],
            lambda d: d["data"],
            lambda d: d["list"],
            lambda d: d["records"],
        ]:
            try:
                val = path(data)
                if isinstance(val, list):
                    return val
            except (KeyError, TypeError):
                continue
        logger.warning("无法从响应中提取列表，原始 keys: %s", list(data.keys()))
        return []

    def _extract_total(self, data: dict) -> int | None:
        for path in [
            lambda d: d["data"]["total"],
            lambda d: d["data"]["totalCount"],
            lambda d: d["total"],
        ]:
            try:
                return int(path(data))
            except (KeyError, TypeError, ValueError):
                continue
        return None


def build_conversation(customer: dict, messages: list[dict]) -> dict:
    """
    Normalize raw API objects into the structure analyzer.py expects:
      { customer_id, agent_name, date, messages: [{role, sender, content, timestamp}] }
    Common field name variants are handled with fallbacks.
    """
    def pick(obj, *keys, default=""):
        for k in keys:
            if obj.get(k) is not None:
                return str(obj[k])
        return default

    customer_id = pick(customer, "uid", "userId", "customerId", "id")
    agent_name = pick(customer, "amName", "agentName", "ownerName", "staffName")
    date = pick(customer, "waLastStartTime", "lastContactTime", "date")

    normalized_msgs = []
    for m in messages:
        # Determine role: look for senderType / fromType / msgType
        sender_type = m.get("senderType") or m.get("fromType") or m.get("msgType") or m.get("type", "")
        # Convention: 0 or "customer" or "user" = customer; 1 or "agent" or "staff" = agent
        is_agent = str(sender_type) in ("1", "agent", "staff", "am", "system")

        content = pick(m, "content", "text", "msgContent", "message", "body")
        timestamp = pick(m, "sendTime", "createTime", "time", "createdAt", "timestamp")
        sender = pick(m, "senderName", "fromName", "staffName", "amName",
                      default="客服" if is_agent else str(customer_id))

        if not content:
            continue

        normalized_msgs.append({
            "role": "agent" if is_agent else "customer",
            "sender": sender,
            "content": content,
            "timestamp": timestamp,
        })

    response_time_flags = _check_response_times(normalized_msgs)

    return {
        "customer_id": customer_id,
        "agent_name": agent_name,
        "date": date,
        "messages": normalized_msgs,
        "response_time_flags": response_time_flags,
    }


def _parse_timestamp(ts: str) -> datetime | None:
    """Try to parse common timestamp formats."""
    if not ts:
        return None
    formats = [
        "%Y-%m-%d %H:%M:%S",
        "%Y/%m/%d %H:%M:%S",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%dT%H:%M:%SZ",
        "%b %d, %Y %I:%M:%S %p",   # May 18, 2026 3:25:33 PM
        "%b %d, %I:%M:%S %p",       # May 18, 3:25:33 PM
        "%d/%m/%Y %H:%M:%S",
        "%m/%d/%Y %H:%M:%S",
    ]
    ts = ts.strip()
    for fmt in formats:
        try:
            return datetime.strptime(ts, fmt)
        except ValueError:
            continue
    # Try unix timestamp (milliseconds)
    try:
        ms = int(re.sub(r"\D", "", ts[:13]))
        return datetime.fromtimestamp(ms / 1000)
    except Exception:
        pass
    return None


def _check_response_times(messages: list[dict]) -> list[str]:
    """
    Detect C3 (>4h no reply) and B6 (>8h no reply) violations.
    Finds each customer message and checks how long until the next agent reply.
    """
    flags = []
    i = 0
    while i < len(messages):
        msg = messages[i]
        if msg["role"] != "customer":
            i += 1
            continue

        customer_ts = _parse_timestamp(msg.get("timestamp", ""))
        if not customer_ts:
            i += 1
            continue

        # Find next agent reply
        agent_ts = None
        for j in range(i + 1, len(messages)):
            if messages[j]["role"] == "agent":
                agent_ts = _parse_timestamp(messages[j].get("timestamp", ""))
                break

        if agent_ts is None:
            # Only flag if there are no subsequent agent messages at all
            # (i.e., agent truly never replied, not just customer didn't respond to agent's last message)
            has_later_agent = any(messages[j]["role"] == "agent" for j in range(i + 1, len(messages)))
            if not has_later_agent:
                pass  # Last message is from customer with no agent reply — skip, may just be end of window
        else:
            gap = agent_ts - customer_ts
            hours = gap.total_seconds() / 3600
            if hours >= 8:
                flags.append(
                    f"客户消息（{msg.get('timestamp','')}）到客服回复间隔 {hours:.1f} 小时，超过8小时（B6）"
                )
            elif hours >= 4:
                flags.append(
                    f"客户消息（{msg.get('timestamp','')}）到客服回复间隔 {hours:.1f} 小时，超过4小时（C3）"
                )

        # Skip to after the agent reply
        i = i + 1
        for j in range(i, len(messages)):
            if messages[j]["role"] == "agent":
                i = j + 1
                break

    return flags
