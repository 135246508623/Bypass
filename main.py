import re
import asyncio
import time
import httpx
from typing import Optional, Dict, Any

# 备用方案：Selenium 使用本地 chromedriver
try:
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    SELENIUM_AVAILABLE = True
except ImportError:
    SELENIUM_AVAILABLE = False

from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, register
from astrbot.api import logger
from astrbot.api.event.filter import EventMessageType

HEADLESS = True   # 无头模式，不显示窗口（加快速度）

@register("astrbot_plugin_bypass", "YourName", "智能解卡机器人（HTTP优先 + 本地Selenium备用）", "5.4.0")
class BypassPlugin(Star):
    def __init__(self, context: Context):
        super().__init__(context)
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
        result = await self.try_all_methods(target_url)
        if result['success']:
            yield event.plain_result(f"✅ 成功！\n{result['result']}")
        else:
            yield event.plain_result(f"❌ 失败: {result['error']}")

    async def try_all_methods(self, url: str) -> Dict[str, Any]:
        # 1. 优先尝试纯 HTTP 请求（快速）
        http_result = await self.try_http(url)
        if http_result['success']:
            logger.info("HTTP 方案成功提取卡密")
            return http_result
        logger.warning(f"HTTP 方案失败: {http_result['error']}")

        # 2. 如果 HTTP 失败且 Selenium 可用，尝试备用方案
        if SELENIUM_AVAILABLE:
            logger.info("尝试 Selenium 备用方案...")
            try:
                selenium_result = await asyncio.to_thread(self._selenium_bypass, url)
                return selenium_result
            except Exception as e:
                logger.error(f"Selenium 备用方案异常: {e}")
                return {'success': False, 'error': f'Selenium 方案异常: {str(e)}; HTTP 失败: {http_result["error"]}'}
        else:
            return {'success': False, 'error': f'HTTP 失败: {http_result["error"]}; Selenium 不可用，请安装 selenium'}

    async def try_http(self, url: str) -> Dict[str, Any]:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
            'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
        }
        try:
            async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
                resp = await client.get(url, headers=headers)
                if resp.status_code == 200:
                    text = resp.text
                    # 提取 FREE_ 格式
                    match = re.search(r'FREE_[a-fA-F0-9]{32}', text, re.IGNORECASE)
                    if match:
                        return {'success': True, 'result': match.group(0)}
                    match = re.search(r'FREE[a-fA-F0-9]{32}', text, re.IGNORECASE)
                    if match:
                        key = match.group(0)
                        if not key.startswith('FREE_'):
                            key = 'FREE_' + key[4:]
                        return {'success': True, 'result': key}
                    if 'Successfully whitelisted' in text:
                        match = re.search(r'FREE_[a-fA-F0-9]{32}', text)
                        if match:
                            return {'success': True, 'result': match.group(0)}
                    return {'success': False, 'error': '未在页面中找到卡密'}
                else:
                    return {'success': False, 'error': f'HTTP {resp.status_code}'}
        except Exception as e:
            logger.error(f"HTTP 请求异常: {e}")
            return {'success': False, 'error': f'请求失败: {str(e)}'}

    # ==================== 备用方案：Selenium 浏览器自动化 ====================
    def _selenium_bypass(self, url: str) -> Dict[str, Any]:
        driver = None
        try:
            # 检查 chromedriver 是否在 PATH 中
            import shutil
            chromedriver_path = shutil.which("chromedriver")
            if not chromedriver_path:
                return {'success': False, 'error': '未找到 chromedriver，请先安装: apt install -y chromium-chromedriver'}

            chrome_options = Options()
            if HEADLESS:
                chrome_options.add_argument('--headless')
            chrome_options.add_argument('--no-sandbox')
            chrome_options.add_argument('--disable-dev-shm-usage')
            chrome_options.add_argument('--disable-gpu')
            chrome_options.add_argument('--window-size=1920,1080')
            chrome_options.add_argument('user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36')
            chrome_options.binary_location = shutil.which("chromium")

            driver = webdriver.Chrome(options=chrome_options)
            driver.set_page_load_timeout(20)

            logger.info(f"备用方案 - 正在访问: {url}")
            driver.get(url)
            WebDriverWait(driver, 15).until(EC.presence_of_element_located((By.TAG_NAME, "body")))

            # 等待页面可能动态加载的内容
            time.sleep(3)
            page_source = driver.page_source
            key = self._extract_key_from_text(page_source)
            if key:
                return {'success': True, 'result': key}

            # 如果还没找到，尝试点击 Continue 按钮（如果有）
            try:
                continue_btn = driver.find_element(By.XPATH, "//button[contains(text(), 'Continue')]")
                continue_btn.click()
                time.sleep(3)
                page_source = driver.page_source
                key = self._extract_key_from_text(page_source)
                if key:
                    return {'success': True, 'result': key}
            except:
                pass

            # 检测成功白名单页面
            if 'Successfully whitelisted' in page_source:
                body_text = driver.find_element(By.TAG_NAME, "body").text
                key_match = re.search(r'FREE_[a-fA-F0-9]{32}', body_text)
                if key_match:
                    return {'success': True, 'result': key_match.group(0)}

            return {'success': False, 'error': '未能提取到卡密'}

        except Exception as e:
            logger.error(f"Selenium 异常: {e}")
            return {'success': False, 'error': f'Selenium 处理异常: {str(e)}'}
        finally:
            if driver:
                driver.quit()

    def _extract_key_from_text(self, text: str) -> Optional[str]:
        match = re.search(r'FREE_[a-fA-F0-9]{32}', text, re.IGNORECASE)
        if match:
            return match.group(0)
        match = re.search(r'FREE[a-fA-F0-9]{32}', text, re.IGNORECASE)
        if match:
            key = match.group(0)
            if not key.startswith('FREE_'):
                key = 'FREE_' + key[4:]
            return key
        return None
