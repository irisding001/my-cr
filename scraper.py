import asyncio
import logging
from datetime import datetime
from typing import Optional

from playwright.async_api import async_playwright, Page, Browser, BrowserContext

logger = logging.getLogger(__name__)


class CRMScraper:
    def __init__(self, base_url: str):
        self.base_url = base_url
        self.playwright = None
        self.browser: Optional[Browser] = None
        self.context: Optional[BrowserContext] = None
        self.page: Optional[Page] = None

    async def start(self):
        self.playwright = await async_playwright().start()
        self.browser = await self.playwright.chromium.launch(
            headless=False,
            args=["--start-maximized"]
        )
        self.context = await self.browser.new_context(
            viewport={"width": 1440, "height": 900},
            locale="zh-CN"
        )
        self.page = await self.context.new_page()

    async def login(self):
        """Open login page, wait for user to complete OTP login manually."""
        await self.page.goto(f"{self.base_url}/login")
        print("\n" + "="*50)
        print("请在浏览器中完成登录：")
        print("  1. 输入用户名和密码")
        print("  2. 输入手机 OTP 验证码")
        print("  3. 登录成功后，回到此窗口按回车继续")
        print("="*50)
        input("\n>>> 登录完成后按回车：")

        if "/login" in self.page.url:
            raise Exception("检测到仍在登录页，请确认登录成功后再试")
        logger.info("登录验证通过，当前 URL: %s", self.page.url)

    async def get_whatsapp_conversations(self, date_str: str) -> list[dict]:
        """Scrape all WhatsApp conversations for the given date."""
        conversations = []
        await self.page.goto(f"{self.base_url}/customer-mgmt/list")
        await self.page.wait_for_load_state("networkidle")

        await self._apply_date_filter(date_str)

        page_num = 1
        while True:
            logger.info("正在抓取第 %d 页...", page_num)
            rows = await self._get_table_rows()
            if not rows:
                logger.info("第 %d 页无数据，停止翻页", page_num)
                break

            for idx, row in enumerate(rows):
                logger.info("  处理第 %d 页第 %d 条记录...", page_num, idx + 1)
                try:
                    conv = await self._process_row(row)
                    if conv and conv.get("messages"):
                        conversations.append(conv)
                except Exception as e:
                    logger.error("  处理记录失败: %s", e)
                    await self.page.screenshot(path=f"output/error_p{page_num}_r{idx}.png")

            if not await self._next_page():
                break
            page_num += 1

        logger.info("共抓取到 %d 条有效对话", len(conversations))
        return conversations

    async def _apply_date_filter(self, date_str: str):
        """Try to set the date filter automatically; fall back to manual."""
        try:
            start = self.page.locator("input[placeholder*='Start Date'], input[placeholder*='开始'], input[placeholder*='start']").first
            end = self.page.locator("input[placeholder*='End Date'], input[placeholder*='结束'], input[placeholder*='end']").first

            if await start.count() > 0:
                await start.fill(date_str)
            if await end.count() > 0:
                await end.fill(date_str)

            search_btn = self.page.locator(
                "button:has-text('Search'), button:has-text('查询'), button:has-text('搜索'), button:has-text('筛选')"
            ).first
            if await search_btn.count() > 0:
                await search_btn.click()
                await self.page.wait_for_load_state("networkidle")
                logger.info("日期筛选已设置为 %s", date_str)
                return
        except Exception as e:
            logger.warning("自动设置日期筛选失败: %s", e)

        print(f"\n请手动将页面日期筛选设置为 {date_str}，然后按回车继续...")
        input(">>> ")

    async def _get_table_rows(self) -> list:
        try:
            await self.page.wait_for_selector("table tbody tr", timeout=8000)
            rows = await self.page.locator("table tbody tr").all()
            return [r for r in rows if await r.is_visible()]
        except Exception:
            return []

    async def _process_row(self, row) -> Optional[dict]:
        """Open contact records for a row and extract WhatsApp messages."""
        # Try clicking the row or a "联系记录" / detail button
        try:
            detail_btn = row.locator(
                "button:has-text('联系'), button:has-text('记录'), a:has-text('详情'), td"
            ).first
            await detail_btn.click()
        except Exception:
            await row.click()

        # Wait for dialog
        try:
            dialog = self.page.locator(
                "[class*='modal']:visible, [class*='drawer']:visible, [class*='dialog']:visible"
            ).first
            await dialog.wait_for(state="visible", timeout=6000)
        except Exception:
            logger.warning("  未找到对话框，跳过")
            return None

        # Click WhatsApp tab
        try:
            wa_tab = self.page.locator(
                "text=whatsapp消息, text=WhatsApp消息, [class*='tab']:has-text('WhatsApp')"
            ).first
            await wa_tab.click()
            await self.page.wait_for_timeout(800)
        except Exception:
            logger.warning("  未找到 WhatsApp 标签页，尝试使用当前内容")

        messages = await self._extract_messages()

        agent_name = next((m["sender"] for m in messages if m["role"] == "agent"), "Unknown")
        customer_id = next((m["sender"] for m in messages if m["role"] == "customer"), "Unknown")

        await self._close_dialog()

        return {
            "customer_id": customer_id,
            "agent_name": agent_name,
            "date": datetime.now().strftime("%Y-%m-%d"),
            "messages": messages,
        }

    async def _extract_messages(self) -> list[dict]:
        """Extract all messages from the visible chat window."""
        messages = []

        # Scroll to load all messages
        for _ in range(5):
            await self.page.keyboard.press("End")
            await self.page.wait_for_timeout(400)

        # Locate message elements — try several common selector patterns
        selectors = [
            "[class*='message-item']",
            "[class*='msg-item']",
            "[class*='chat-item']",
            "[class*='bubble']",
            ".ant-comment",
        ]
        msg_els = []
        for sel in selectors:
            els = await self.page.locator(sel).all()
            if els:
                msg_els = els
                break

        if not msg_els:
            # Fallback: grab all visible text blocks inside the dialog
            logger.warning("  使用通用文本块提取消息")
            return await self._fallback_extract()

        for el in msg_els:
            try:
                # Determine sender side (agent = right/blue, customer = left)
                class_attr = await el.get_attribute("class") or ""
                style_attr = await el.get_attribute("style") or ""
                is_agent = (
                    "right" in class_attr.lower()
                    or "agent" in class_attr.lower()
                    or "self" in class_attr.lower()
                    or await el.evaluate(
                        "el => { const s = window.getComputedStyle(el); "
                        "return s.justifyContent === 'flex-end' || s.textAlign === 'right'; }"
                    )
                )

                text_el = el.locator("[class*='content'], [class*='text'], [class*='body'], p, span").first
                text = await text_el.inner_text() if await text_el.count() > 0 else await el.inner_text()
                text = text.strip()
                if not text:
                    continue

                time_el = el.locator("[class*='time'], [class*='timestamp'], [class*='date']").first
                timestamp = (await time_el.inner_text()).strip() if await time_el.count() > 0 else ""

                name_el = el.locator("[class*='name'], [class*='sender'], [class*='user']").first
                sender = (await name_el.inner_text()).strip() if await name_el.count() > 0 else (
                    "客服" if is_agent else "客户"
                )

                messages.append({
                    "role": "agent" if is_agent else "customer",
                    "sender": sender,
                    "content": text,
                    "timestamp": timestamp,
                })
            except Exception as e:
                logger.debug("  解析消息元素失败: %s", e)

        return messages

    async def _fallback_extract(self) -> list[dict]:
        """Last-resort extraction: dump all visible text in the dialog."""
        try:
            dialog_text = await self.page.locator(
                "[class*='modal']:visible, [class*='dialog']:visible, [class*='drawer']:visible"
            ).first.inner_text()
            return [{
                "role": "unknown",
                "sender": "unknown",
                "content": dialog_text,
                "timestamp": "",
            }]
        except Exception:
            return []

    async def _close_dialog(self):
        try:
            close = self.page.locator(
                "button[aria-label='Close'], button[class*='close'], .ant-modal-close, "
                "[class*='close-btn'], button:has-text('关闭')"
            ).first
            if await close.count() > 0:
                await close.click()
            else:
                await self.page.keyboard.press("Escape")
            await self.page.wait_for_timeout(500)
        except Exception:
            await self.page.keyboard.press("Escape")

    async def _next_page(self) -> bool:
        try:
            nxt = self.page.locator(
                "li[class*='next']:not([class*='disabled']), "
                "button[class*='next']:not([disabled]), "
                ".ant-pagination-next:not(.ant-pagination-disabled)"
            ).first
            if await nxt.count() > 0 and await nxt.is_enabled():
                await nxt.click()
                await self.page.wait_for_load_state("networkidle")
                return True
        except Exception:
            pass
        return False

    async def close(self):
        if self.browser:
            await self.browser.close()
        if self.playwright:
            await self.playwright.stop()
