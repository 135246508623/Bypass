import re
import asyncio
import httpx
from typing import Optional, Dict, Any
from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, register
from astrbot.api import logger
from astrbot.api.event.filter import EventMessageType

# 可选依赖：Selenium（手机环境一般不用，但保留代码）
try:
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    import undetected_chromedriver as uc
    SELENIUM_AVAILABLE = False   # 手机环境默认关闭，如需开启改为 True 并安装依赖
except ImportError:
    SELENIUM_AVAILABLE = False

@register("astrbot_plugin_bypass", "YourName", "全能卡密获取器（优化卡密提取）", "2.1.0")
class BypassPlugin(Star):
    def __init__(self, context: Context):
        super().__init__(context)
        # ==================== API 端点池（按优先级） ====================
        self.api_endpoints = [
            "https://bypass.vip/api/bypass",
            "https://bypass.vip/bypass",
            "https://bypassunlock.com/api/bypass",
            "https://api.bypass.city/v1/bypass",
            "https://api.izen.lol/bypass",
            "https://api.izen.lol/v1/bypass",
            "https://api.izen.lol/bypassv2",
            "https://zen-api.bypass.lol/bypass",
            "https://api.bypass.vip/v2/bypass",
            "https://api.bypass.vip/v3/bypass",
        ]
        # ==================== 本地自建 API（可选） ====================
        self.local_api_url = None   # 例如 "http://127.0.0.1:5000/bypass"
        # ==================== 限频设置 ====================
        self.timeout = 15.0
        self.group_last_call = {}

    # -------------------- 消息入口 --------------------
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

        # 限频（每群每30秒最多1次）
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

    # -------------------- 主控：依次尝试所有方法 --------------------
    async def try_all_methods(self, url: str) -> Dict[str, Any]:
        # 1. 尝试第三方 API 池
        for endpoint in self.api_endpoints:
            key = await self.try_api(endpoint, url)
            if key:
                logger.info(f"API {endpoint} 成功获取卡密: {key}")
                return {'success': True, 'result': key}
        
        # 2. 尝试本地自建 API（如果配置了）
        if self.local_api_url:
            key = await self.try_local_api(url)
            if key:
                logger.info(f"本地 API 成功获取卡密: {key}")
                return {'success': True, 'result': key}
        
        # 3. 尝试 Selenium（如果开启）
        if SELENIUM_AVAILABLE:
            key = await self.try_selenium(url)
            if key:
                logger.info(f"Selenium 成功获取卡密: {key}")
                return {'success': True, 'result': key}
        
        return {'success': False, 'error': '所有绕过方法均失败，请稍后重试或手动访问'}

    # -------------------- 方法1：调用第三方 API --------------------
    async def try_api(self, endpoint: str, url: str) -> Optional[str]:
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.get(endpoint, params={'url': url})
                if resp.status_code == 200:
                    # 打印前500字符便于调试（可在日志中查看）
                    logger.debug(f"API {endpoint} 返回: {resp.text[:500]}")
                    return self._extract_key_from_text(resp.text)
        except Exception as e:
            logger.warning(f"API {endpoint} 请求异常: {e}")
        return None

    # -------------------- 方法2：本地自建 API --------------------
    async def try_local_api(self, url: str) -> Optional[str]:
        if not self.local_api_url:
            return None
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.get(self.local_api_url, params={'url': url})
                if resp.status_code == 200:
                    return self._extract_key_from_text(resp.text)
        except Exception as e:
            logger.warning(f"本地 API 请求失败: {e}")
        return None

    # -------------------- 方法3：Selenium（半自动，手机慎用） --------------------
    async def try_selenium(self, url: str) -> Optional[str]:
        if not SELENIUM_AVAILABLE:
            return None
        # 由于 Selenium 是阻塞的，放到线程池执行
        return await asyncio.to_thread(self._selenium_bypass, url)

    def _selenium_bypass(self, url: str) -> Optional[str]:
        driver = None
        try:
            options = uc.ChromeOptions()
            options.add_argument('--headless')  # 无头模式，如需手动验证码可去掉
            options.add_argument('--no-sandbox')
            options.add_argument('--disable-dev-shm-usage')
            driver = uc.Chrome(options=options)
            driver.get(url)
            WebDriverWait(driver, 15).until(EC.presence_of_element_located((By.TAG_NAME, "body")))
            # 尝试点击 Continue 按钮
            for xpath in [
                "//button[contains(text(), 'Continue')]",
                "//button[contains(text(), '继续')]",
                "//a[contains(text(), 'Continue')]"
            ]:
                try:
                    btn = driver.find_element(By.XPATH, xpath)
                    btn.click()
                    break
                except:
                    pass
            asyncio.sleep(3)  # 等待页面更新
            page_text = driver.page_source
            return self._extract_key_from_text(page_text)
        except Exception as e:
            logger.warning(f"Selenium 绕过失败: {e}")
            return None
        finally:
            if driver:
                driver.quit()

    # -------------------- 增强版卡密提取 --------------------
    def _extract_key_from_text(self, text: str) -> Optional[str]:
        """
        从响应文本中提取卡密，支持多种格式：
        - FREE_ 后跟32位十六进制
        - FREE 无下划线后跟32位十六进制
        - 纯32位十六进制（自动补 FREE_）
        - 20~40位字母数字组合
        - 纯链接
        """
        # 1. 尝试 JSON 解析
        try:
            import json
            data = json.loads(text)
            if data.get('success') and data.get('result'):
                return data['result']
