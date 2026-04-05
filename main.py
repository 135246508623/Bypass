import re
import asyncio
import time
from typing import Optional, Dict, Any

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

# ========== 配置 ==========
HEADLESS = False   # 半自动模式（遇到验证码时手动处理）建议 False；全自动可设为 True
# ========================

@register("astrbot_plugin_bypass", "YourName", "全自动解卡机器人（Selenium + webdriver-manager）", "3.1.0")
class BypassPlugin(Star):
    def __init__(self, context: Context):
        super().__init__(context)
        # 支持的链接域名
        self.link_patterns = [
            r'auth\.platorelay\.com',
            r'auth\.platoboost\.(?:com|net|click|app|me)',
            r'deltaios-executor\.com',
            r'linkvertise\.com',
            r'work\.ink',
            r'loot-link\.com',
            r'rekonise\.com',
        ]
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
        result = await self.process_link(target_url)
        if result['success']:
            yield event.plain_result(f"✅ 成功！\n{result['result']}")
        else:
            yield event.plain_result(f"❌ 失败: {result['error']}")

    async def process_link(self, url: str) -> Dict[str, Any]:
        is_supported = any(re.search(pattern, url, re.I) for pattern in self.link_patterns)
        if not is_supported:
            return {'success': False, 'error': '不支持的链接类型'}
        return await asyncio.to_thread(self._selenium_bypass, url)

    def _selenium_bypass(self, url: str) -> Dict[str, Any]:
        driver = None
        try:
            # 配置 Chrome 选项
            chrome_options = Options()
            if HEADLESS:
                chrome_options.add_argument('--headless')
            chrome_options.add_argument('--no-sandbox')
            chrome_options.add_argument('--disable-dev-shm-usage')
            chrome_options.add_argument('--disable-gpu')
            chrome_options.add_argument('--window-size=1920,1080')
            chrome_options.add_argument('user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36')
            # 自动管理 ChromeDriver
            service = Service(ChromeDriverManager().install())
            driver = webdriver.Chrome(service=service, options=chrome_options)

            logger.info(f"正在访问: {url}")
            driver.get(url)
            WebDriverWait(driver, 15).until(EC.presence_of_element_located((By.TAG_NAME, "body")))

            # 尝试点击 Continue 按钮
            continue_selectors = [
                "//button[contains(text(), 'Continue')]",
                "//button[contains(text(), '继续')]",
                "//a[contains(text(), 'Continue')]",
                "//*[@id='continueBtn']"
            ]
            for selector in continue_selectors:
                try:
                    btn = WebDriverWait(driver, 5).until(EC.element_to_be_clickable((By.XPATH, selector)))
                    btn.click()
                    logger.info("已点击 Continue 按钮")
                    break
                except:
                    pass

            time.sleep(5)

            # 检测验证码（半自动模式）
            page_source = driver.page_source
            if 'hcaptcha' in page_source.lower() or 'recaptcha' in page_source.lower():
                logger.info("检测到验证码，进入半自动处理模式")
                if not HEADLESS:
                    input("⚠️ 请在浏览器中手动完成验证码，完成后按回车键继续...")
                else:
                    return {'success': False, 'error': '需要验证码，请稍后重试或使用半自动模式'}

            time.sleep(8)
            key = self._extract_key_from_text(driver.page_source)
            if key:
                return {'success': True, 'result': key}
            time.sleep(5)
            key = self._extract_key_from_text(driver.page_source)
            if key:
                return {'success': True, 'result': key}
            return {'success': False, 'error': '未能提取到卡密'}

        except Exception as e:
            logger.error(f"Selenium 异常: {e}")
            return {'success': False, 'error': f'处理异常: {str(e)}'}
        finally:
            if driver:
                driver.quit()

    def _extract_key_from_text(self, text: str) -> Optional[str]:
        match = re.search(r'FREE_?[a-fA-F0-9]{32}', text, re.IGNORECASE)
        if match:
            key = match.group(0)
            if not key.startswith('FREE_'):
                key = 'FREE_' + key[4:]
            return key
        match = re.search(r'\b[a-fA-F0-9]{32}\b', text)
        if match:
            return f"FREE_{match.group(0)}"
        match = re.search(r'\b[A-Za-z0-9]{20,40}\b', text)
        if match:
            return match.group(0)
        return None
