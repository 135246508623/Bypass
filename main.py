import re
import asyncio
import httpx
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.chrome.service import Service
from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, register
from astrbot.api import logger
from astrbot.api.event.filter import EventMessageType

@register("astrbot_plugin_bypass", "YourName", "智能解卡（HTTP+浏览器+Copy点击）", "7.2.0")
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
        result = await self.try_all(target_url)
        if result['success']:
            yield event.plain_result(f"✅ 成功！\n{result['result']}")
        else:
            yield event.plain_result(f"❌ 失败: {result['error']}")

    async def try_all(self, url: str):
        # 1. HTTP 请求提取
        http_key = await self.try_http(url)
        if http_key:
            return {'success': True, 'result': http_key}
        logger.info("HTTP 未提取到卡密，启动浏览器方案...")
        # 2. 浏览器方案
        return await asyncio.to_thread(self._browser_bypass, url)

    async def try_http(self, url: str):
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
        try:
            async with httpx.AsyncClient(timeout=10, follow_redirects=True) as client:
                resp = await client.get(url, headers=headers)
                if resp.status_code == 200:
                    return self._extract_key_from_html(resp.text)
        except Exception as e:
            logger.debug(f"HTTP 请求失败: {e}")
        return None

    def _extract_key_from_html(self, html: str) -> str | None:
        """从 HTML 源码中提取 FREE_ 格式的卡密"""
        match = re.search(r'FREE_[a-fA-F0-9]{32}', html, re.IGNORECASE)
        if match:
            return match.group(0)
        # 兼容无下划线格式
        match = re.search(r'FREE[a-fA-F0-9]{32}', html, re.IGNORECASE)
        if match:
            key = match.group(0)
            if not key.startswith('FREE_'):
                key = 'FREE_' + key[4:]
            return key
        return None

    def _browser_bypass(self, url: str):
        driver = None
        try:
            options = Options()
            options.add_argument('--headless')
            options.add_argument('--no-sandbox')
            options.add_argument('--disable-dev-shm-usage')
            options.binary_location = "/usr/bin/chromium"
            service = Service(ChromeDriverManager().install())
            driver = webdriver.Chrome(service=service, options=options)
            driver.get(url)

            # 等待页面加载
            WebDriverWait(driver, 15).until(EC.presence_of_element_located((By.TAG_NAME, "body")))
            import time

            # 首先从当前页面源码提取卡密
            page_source = driver.page_source
            key = self._extract_key_from_html(page_source)
            if key:
                logger.info("直接从页面源码提取到卡密")
                return {'success': True, 'result': key}

            # 如果没有，尝试点击 Copy 按钮
            try:
                copy_btn = WebDriverWait(driver, 10).until(
                    EC.element_to_be_clickable((By.XPATH, "//button[contains(translate(text(), 'COPY', 'copy'), 'copy')]"))
                )
                copy_btn.click()
                logger.info("已点击 Copy 按钮")
                time.sleep(2)
                page_source = driver.page_source
                key = self._extract_key_from_html(page_source)
                if key:
                    return {'success': True, 'result': key}
                else:
                    return {'success': False, 'error': '点击 Copy 后仍未找到卡密'}
            except Exception as e:
                logger.warning(f"未找到 Copy 按钮或点击失败: {e}")
                return {'success': False, 'error': '未找到 Copy 按钮且页面无卡密'}

        except Exception as e:
            logger.error(f"浏览器方案异常: {e}")
            return {'success': False, 'error': f'浏览器方案失败: {str(e)}'}
        finally:
            if driver:
                driver.quit()
