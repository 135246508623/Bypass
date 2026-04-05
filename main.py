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

HEADLESS = False

@register("astrbot_plugin_bypass", "YourName", "智能解卡机器人（自动点击Copy按钮）", "4.5.0")
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
            chrome_options = Options()
            if HEADLESS:
                chrome_options.add_argument('--headless')
            chrome_options.add_argument('--no-sandbox')
            chrome_options.add_argument('--disable-dev-shm-usage')
            chrome_options.add_argument('--disable-gpu')
            chrome_options.add_argument('--window-size=1920,1080')
            chrome_options.add_argument('user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36')
            chrome_options.binary_location = "/usr/bin/chromium"

            service = Service(ChromeDriverManager().install())
            driver = webdriver.Chrome(service=service, options=chrome_options)

            logger.info(f"正在访问: {url}")
            driver.get(url)
            WebDriverWait(driver, 15).until(EC.presence_of_element_located((By.TAG_NAME, "body")))

            max_clicks = 5
            click_count = 0
            last_url = driver.current_url

            while click_count < max_clicks:
                page_source = driver.page_source
                key = self._extract_key_from_text(page_source)
                if key:
                    logger.info(f"成功提取卡密: {key}")
                    return {'success': True, 'result': key}

                # 检测成功白名单页面
                if 'Successfully whitelisted' in page_source:
                    logger.info("检测到成功白名单页面，等待卡密出现...")
                    time.sleep(3)
                    key = self._extract_key_from_text(driver.page_source)
                    if key:
                        return {'success': True, 'result': key}
                    # 尝试从 body 文本中提取
                    body_text = driver.find_element(By.TAG_NAME, "body").text
                    key_match = re.search(r'FREE_[a-fA-F0-9]{32}', body_text)
                    if key_match:
                        return {'success': True, 'result': key_match.group(0)}

                # 检测验证码或广告任务
                if 'hcaptcha' in page_source.lower() or 'recaptcha' in page_source.lower():
                    logger.info("检测到验证码，进入半自动处理模式")
                    if not HEADLESS:
                        input("⚠️ 请在浏览器中手动完成验证码，完成后按回车键继续...")
                        continue
                    else:
                        return {'success': False, 'error': '需要验证码，请稍后重试或使用半自动模式'}
                elif '点击并发送短信' in page_source or '接受通知' in page_source:
                    logger.info("检测到广告任务列表，请手动完成")
                    if not HEADLESS:
                        input("⚠️ 请在浏览器中手动完成所有任务，完成后按回车键继续...")
                        continue
                    else:
                        return {'success': False, 'error': '需要手动完成任务，请使用半自动模式'}

                # ========== 优先查找 Copy 按钮 ==========
                copy_buttons = driver.find_elements(By.XPATH, "//button[contains(text(), 'Copy') or contains(text(), '复制')] | //a[contains(text(), 'Copy') or contains(text(), '复制')]")
                for btn in copy_buttons:
                    if btn.is_displayed() and btn.is_enabled():
                        logger.info(f"发现 Copy 按钮: {btn.text}, 自动点击...")
                        try:
                            btn.click()
                            # 点击后，卡密可能被复制到剪贴板，但页面文本中通常已经存在，直接提取
                            time.sleep(1)
                            key = self._extract_key_from_text(driver.page_source)
                            if key:
                                return {'success': True, 'result': key}
                            else:
                                # 如果仍然没有，可能卡密在另一个元素中，尝试查找包含 FREE_ 的文本
                                body_text = driver.find_element(By.TAG_NAME, "body").text
                                key_match = re.search(r'FREE_[a-fA-F0-9]{32}', body_text)
                                if key_match:
                                    return {'success': True, 'result': key_match.group(0)}
                        except Exception as e:
                            logger.warning(f"点击 Copy 按钮失败: {e}")

                # ========== 自动点击唯一按钮（排除 Continue 等） ==========
                buttons = driver.find_elements(By.XPATH, "//button | //a | //input[@type='button' or @type='submit']")
                visible_buttons = [btn for btn in buttons if btn.is_displayed() and btn.is_enabled()]
                # 过滤掉常见的“继续”按钮
                filtered = []
                for btn in visible_buttons:
                    text = btn.text.strip().lower()
                    if text not in ['continue', '继续', 'next', '下一步']:
                        filtered.append(btn)

                if len(filtered) == 1:
                    btn = filtered[0]
                    logger.info(f"发现唯一按钮: {btn.text}, 自动点击...")
                    try:
                        btn.click()
                        click_count += 1
                        time.sleep(3)
                        if driver.current_url == last_url:
                            logger.warning("点击后 URL 未变化，可能点击无效")
                        last_url = driver.current_url
                        continue
                    except Exception as e:
                        logger.warning(f"点击按钮失败: {e}")

                # 没有可点击的按钮或按钮数量不为1，等待后重试
                logger.info("未找到 Copy 按钮或唯一可点击按钮，等待5秒后重试...")
                time.sleep(5)
                click_count += 1

            # 最终再尝试提取一次卡密
            time.sleep(5)
            key = self._extract_key_from_text(driver.page_source)
            if key:
                return {'success': True, 'result': key}
            else:
                return {'success': False, 'error': '未能提取到卡密，可能任务未完成或页面超时'}

        except Exception as e:
            logger.error(f"Selenium 异常: {e}")
            return {'success': False, 'error': f'处理异常: {str(e)}'}
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
        match = re.search(r'\b[a-fA-F0-9]{32}\b', text)
        if match:
            return f"FREE_{match.group(0)}"
        match = re.search(r'\b[A-Za-z0-9]{20,40}\b', text)
        if match:
            return match.group(0)
        return None
