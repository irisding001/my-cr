"""
moomoo WhatsApp 客服质检系统
用法:
  python main.py                      # 质检今天
  python main.py --date 2026-05-17    # 质检指定日期
  python main.py --from-file raw.json # 跳过抓取，直接分析已有数据
"""
import json
import logging
import os
import sys
from datetime import datetime

from config import OUTPUT_DIR, TARGET_AGENTS
from api_client import APIClient, build_conversation
from analyzer import analyze_conversation
from reporter import generate_excel, generate_dashboard

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

COOKIES_FILE = "cookies.txt"


def load_cookies() -> str:
    if not os.path.exists(COOKIES_FILE):
        print(f"错误：找不到 {COOKIES_FILE}")
        print("请将浏览器 Cookie 字符串粘贴到 cookies.txt 文件中")
        sys.exit(1)
    content = open(COOKIES_FILE, encoding="utf-8").read().strip()
    if "EGG_SESS" not in content:
        print("错误：cookies.txt 中未检测到有效 Cookie（需包含 EGG_SESS）")
        print("请重新从浏览器 Network 面板复制 Cookie 字符串")
        sys.exit(1)
    return content


def fetch_conversations(client: APIClient, date_str: str) -> list[dict]:
    """Pull customer list then fetch WhatsApp messages for each customer."""
    api_date = date_str.replace("-", "")  # YYYYMMDD
    customers = client.get_customer_list(api_date)

    if not customers:
        logger.warning("客户列表为空，请检查日期或 Cookie 是否有效")
        return []

    conversations = []
    total = len(customers)
    for i, customer in enumerate(customers, 1):
        uid = (
            customer.get("uid")
            or customer.get("userId")
            or customer.get("customerId")
            or customer.get("id")
        )
        if not uid:
            logger.warning("[%d/%d] 无法获取 uid，跳过: %s", i, total, customer)
            continue

        logger.info("[%d/%d] 获取消息 uid=%s ...", i, total, uid)
        try:
            messages = client.get_whatsapp_messages(str(uid))
            if not messages:
                logger.info("  uid=%s 无消息，跳过", uid)
                continue
            conv = build_conversation(customer, messages)
            conv["date"] = date_str
            conversations.append(conv)
        except Exception as e:
            logger.error("  uid=%s 获取失败: %s", uid, e)

    return conversations


def _analyze_one(args):
    i, total, conv = args
    cid = conv.get("customer_id", "?")
    agent = conv.get("agent_name", "?")
    logger.info("[%d/%d] 质检 customer=%s agent=%s ...", i, total, cid, agent)
    try:
        return analyze_conversation(conv)
    except Exception as e:
        logger.error("  分析失败 customer=%s: %s", cid, e)
        return {
            "customer_id": cid,
            "agent_name": agent,
            "date": conv.get("date", ""),
            "violations": [],
            "attitude_score": None,
            "resolution_status": "无法分析",
            "complaint_risk": "无法判断",
            "summary": f"分析失败: {e}",
            "action_required": False,
            "action_detail": None,
        }


def run_analysis(conversations: list[dict]) -> list[dict]:
    from concurrent.futures import ThreadPoolExecutor, as_completed
    total = len(conversations)
    args = [(i, total, conv) for i, conv in enumerate(conversations, 1)]
    results = [None] * total
    with ThreadPoolExecutor(max_workers=3) as pool:
        futures = {pool.submit(_analyze_one, a): a[0] - 1 for a in args}
        for fut in as_completed(futures):
            idx = futures[fut]
            results[idx] = fut.result()
    return results


def parse_args():
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--date", default=datetime.now().strftime("%Y-%m-%d"))
    p.add_argument("--from-file", metavar="FILE")
    p.add_argument("--limit", type=int, default=0, help="只分析前N条，0=全部")
    return p.parse_args()


def main():
    args = parse_args()
    date_str = args.date
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    raw_path = os.path.join(OUTPUT_DIR, f"raw_{date_str}.json")
    qc_path = os.path.join(OUTPUT_DIR, f"qc_results_{date_str}.json")
    excel_path = os.path.join(OUTPUT_DIR, f"质检报告_{date_str}.xlsx")
    dashboard_path = os.path.join(OUTPUT_DIR, f"质检日报_{date_str}.html")

    # --- Step 1: Get raw conversations ---
    if args.from_file:
        logger.info("从文件读取: %s", args.from_file)
        conversations = json.load(open(args.from_file, encoding="utf-8"))
    elif os.path.exists(raw_path):
        logger.info("从缓存读取: %s", raw_path)
        conversations = json.load(open(raw_path, encoding="utf-8"))
    else:
        cookie_str = load_cookies()
        client = APIClient(cookie_str)
        logger.info("开始拉取 %s 的 WhatsApp 对话...", date_str)
        conversations = fetch_conversations(client, date_str)
        json.dump(conversations, open(raw_path, "w", encoding="utf-8"),
                  ensure_ascii=False, indent=2)
        logger.info("原始数据已保存: %s（%d 条）", raw_path, len(conversations))

    if not conversations:
        logger.warning("无对话数据，程序退出")
        sys.exit(0)

    if args.limit > 0:
        conversations = conversations[:args.limit]
        logger.info("限制分析前 %d 条", args.limit)

    # Filter to target agents only
    before = len(conversations)
    conversations = [c for c in conversations if (c.get("agent_name") or "").lower() in TARGET_AGENTS]
    logger.info("按人员过滤：%d → %d 条", before, len(conversations))

    # Cap each agent to 50 conversations
    from collections import defaultdict
    agent_counts: dict[str, int] = defaultdict(int)
    capped = []
    for conv in conversations:
        agent = conv.get("agent_name") or "unknown"
        if agent_counts[agent] < 50:
            capped.append(conv)
            agent_counts[agent] += 1
    if len(capped) < len(conversations):
        logger.info("每人限50条：%d → %d 条", len(conversations), len(capped))
    conversations = capped

    # --- Step 2: AI quality check ---
    logger.info("开始 AI 质检，共 %d 条对话...", len(conversations))
    qc_results = run_analysis(conversations)
    json.dump(qc_results, open(qc_path, "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)

    # --- Step 3: Generate reports ---
    generate_dashboard(qc_results, dashboard_path, date_str)

    print("\n" + "=" * 50)
    print(f"质检完成！共处理 {len(qc_results)} 条对话")
    print(f"  Excel:     {excel_path}")
    print(f"  Dashboard: {dashboard_path}")
    print("=" * 50)


if __name__ == "__main__":
    main()
