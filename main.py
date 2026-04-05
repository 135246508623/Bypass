import re
import asyncio
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.chrome.service import Service
from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, register
from astrbot.api import logger
from astrbot.api.event.filter import EventMessageType

@register("astrbot_plugin_bypass", "YourName", "自动驱动解卡（含Copy点击）", "6.3.0")
class BypassPlugin(Star):
    def __init__(self, context: Context):
        super().__init__(context)
        self.group_last_call = {}

    @filter.event_message_type(EventMessageType.GROUP_MESSAGE)
    async def on_group_message(self, event: AstrMessageEvent):
        message = event.message_str.strip()
        if not message.lower().startswith('/getkey'):
            return
        parts = message.split(maxsplit=1)
        if len(parts) < 2:
            yield event.plain_result("❌ 用法：/getkey <链接>")
            return
        target_url = parts[1].strip()

        group_id = event.message_obj.group_id
        now = event.message_obj.timestamp
        if group_id in self.group_last_call:
            if now - self.group_last_call[group_id] < 30:
                yield event.plain_result("请求过于频繁，请稍后再试")
                return
        self.group_last_call[group_id] = now

        yield event.plain_result("🔍 正在处理，请稍候...")
        result = await asyncio.to_thread(self._get_key, target_url)
        if result['success']:
            yield event.plain_result(f"✅ 成功！\n{result['result']}")
        else:
            yield event.plain_result(f"❌ 失败: {result['error']}")

    def _get_key(self, url):
        try:
            options = Options()
            options.add_argument('--headless')
            options.add_argument('--no-sandbox')
            options.add_argument('--disable-dev-shm-usage')
            options.binary_location = "/usr/bin/chromium"

            service = Service(ChromeDriverManager().install())
            driver = webdriver.Chrome(service=service, options=options)

            driver.get(url)
            driver.implicitly_wait(10)
            import time
            time.sleep(5)

            # 点击 Copy 按钮（如果有）
            try:
                copy_btn = driver.find_element(By.XPATH, "//button[contains(text(), 'Copy') or contains(text(), '复制')]")
                copy_btn.click()
                logger.info("已点击 Copy 按钮")
                time.sleep(0.5)
            except Exception as e:
                logger.warning(f"未找到 Copy 按钮或点击失败: {e}")

            page_text = driver.page_source
            driver.quit()

            match = re.search(r'FREE_[a-fA-F0-9]{32}', page_text, re.IGNORECASE)
            if match:
                return {'success': True, 'result': match.group(0)}
            return {'success': False, 'error': '未找到卡密'}
        except Exception as e:
            return {'success': False, 'error': str(e)}
