import re
import asyncio
import subprocess
import sys
from typing import Optional, Dict, Any

import httpx
from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, register
from astrbot.api import logger
from astrbot.api.event.filter import EventMessageType

# ---------- 依赖自动检测与安装 ----------
def ensure_package(package: str) -> bool:
    """尝试导入包，如果失败则尝试用 pip 安装"""
    try:
        __import__(package)
        return True
    except ImportError:
        logger.warning(f"未找到 {package}，尝试自动安装...")
        try:
            subprocess.check_call([sys.executable, "-m", "pip", "install", package])
            logger.info(f"{package} 安装成功，请重启 AstrBot 以生效")
            return False  # 当前会话仍未导入，需要重启
        except Exception as e:
            logger.error(f"自动安装 {package} 失败: {e}，请手动执行: pip install {package}")
            return False

# 检测 httpx（必需）
if not ensure_package("httpx"):
    logger.error("httpx 安装失败，插件将无法正常工作")

# 可选依赖：selenium（用于备用绕过，不强求）
SELENIUM_AVAILABLE = ensure_package("selenium")
if SELENIUM_AVAILABLE:
    try:
        from selenium import webdriver
        from selenium.webdriver.chrome.options import Options
        from selenium.webdriver.common.by import By
        from selenium.webdriver.support.ui import WebDriverWait
        from selenium.webdriver.support import expected_conditions as EC
        # 检测 Chrome 浏览器是否存在
        import shutil
        if not shutil.which("chromedriver") and not shutil.which("chromium-browser"):
            logger.warning("未找到 Chrome/Chromium 浏览器，Selenium 功能将被禁用")
            SELENIUM_AVAILABLE = False
    except Exception as e:
        logger.warning(f"Selenium 初始化失败: {e}")
        SELENIUM_AVAILABLE = False

@register("astrbot_plugin_bypass", "YourName", "卡密获取器（仅指令触发）", "3.0.0")
class BypassPlugin(Star):
    def __init__(self, context: Context):
        super().__init__(context)
        # API 端点池
        self.api_endpoints = [
            "https://bypass.vip/api/bypass",
            "https://bypass.vip/bypass",
            "https://bypassunlock.com/api/bypass",
            "https://api.bypass.city/v1/bypass",
            "https://api.izen.lol/bypass",
        ]
        self.timeout = 15.0
        self.group_last_call = {}

    @filter.event_message_type(EventMessageType.GROUP_MESSAGE)
    async def on_group_message(self, event: AstrMessageEvent):
        message = event.message_str.strip()
        # 只响应 /getkey 指令，不处理任何其他内容
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
        # 优先尝试 API 端点
        for endpoint in self.api_endpoints:
            key = await self.try_api(endpoint, url)
            if key:
                logger.info(f"API {endpoint} 成功获取卡密: {key}")
                return {'success': True, 'result': key}
        # 如果 API 都失败且 Selenium 可用，尝试 Selenium（备用）
        if SELENIUM_AVAILABLE:
            key = await self.try_selenium(url)
            if key:
                return {'success': True, 'result': key}
        return {'success': False, 'error': '所有绕过方法均失败，请稍后重试'}

    async def try_api(self, endpoint: str, url: str) -> Optional[str]:
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.get(endpoint, params={'url': url})
                if resp.status_code == 200:
                    # 只信任 JSON 中的 key 或 result 字段
                    try:
                        data = resp.json()
                        if data.get('key'):
                            return data['key']
                        if data.get('result'):
                            return data['result']
                    except:
                        logger.debug(f"API {endpoint} 返回非 JSON 内容")
        except Exception as e:
            logger.warning(f"API {endpoint} 请求异常: {e}")
        return None

    async def try_selenium(self, url: str) -> Optional[str]:
        return await asyncio.to_thread(self._selenium_bypass, url)

    def _selenium_bypass(self, url: str) -> Optional[str]:
        try:
            from selenium import webdriver
            from selenium.webdriver.chrome.options import Options
            options = Options()
            options.add_argument('--headless')
            driver = webdriver.Chrome(options=options)
            driver.get(url)
            driver.implicitly_wait(10)
            page_text = driver.page_source
            driver.quit()
            # 尝试从页面中提取 JSON 块
            try:
                import json
                json_match = re.search(r'\{.*"key".*\}', page_text)
                if json_match:
                    data = json.loads(json_match.group())
                    return data.get('key') or data.get('result')
            except:
                pass
            # 备用：匹配 FREE_ 格式（如果实在需要）
            match = re.search(r'FREE_?[a-fA-F0-9]{32}', page_text)
            if match:
                key = match.group(0)
                if not key.startswith('FREE_'):
                    key = 'FREE_' + key[4:]
                return key
            return None
        except Exception as e:
            logger.warning(f"Selenium 绕过失败: {e}")
            return None
