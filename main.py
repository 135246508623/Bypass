import re
import asyncio
import time
from typing import Optional, Dict, Any

import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, register
from astrbot.api import logger
from astrbot.api.event.filter import EventMessageType

# 可选：2Captcha 集成（需要注册并安装 twocaptcha 库）
# pip install twocaptcha
# from twocaptcha import TwoCaptcha
# CAPTCHA_API_KEY = "YOUR_2CAPTCHA_API_KEY"
# solver = TwoCaptcha(CAPTCHA_API_KEY) if CAPTCHA_API_KEY != "YOUR_2CAPTCHA_API_KEY" else None

# 是否使用无头模式（不显示浏览器窗口，半自动模式建议设为 False）
HEADLESS = False   # 半自动模式时设为 False，以便手动处理验证码

@register("astrbot_plugin_bypass", "YourName", "全自动解卡机器人（内置浏览器）", "3.0.0")
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
        # 限频记录
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

        # 限频（每群每30秒最多1次）
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
        """主处理函数：使用 Selenium 模拟浏览器"""
        # 简单校验链接类型
        is_supported = any(re.search(pattern, url, re.I) for pattern in self.link_patterns)
        if not is_supported:
            return {'success': False, 'error': '不支持的链接类型'}

        # 使用线程池运行 Selenium 任务（阻塞操作）
        return await asyncio.to_thread(self._selenium_bypass, url)

    def _selenium_bypass(self, url: str) -> Dict[str, Any]:
        """Selenium 核心逻辑：自动点击、等待、提取卡密，支持半自动验证码"""
        driver = None
        try:
            # 配置 Chrome
            options = uc.ChromeOptions()
            if HEADLESS:
                options.add_argument('--headless')
            else:
                # 半自动模式：显示浏览器窗口，方便手动处理验证码
                options.add_argument('--no-sandbox')
                options.add_argument('--disable-dev-shm-usage')
            options.add_argument('--disable-gpu')
            options.add_argument('--window-size=1920,1080')
            options.add_argument('user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36')
            driver = uc.Chrome(options=options)

            logger.info(f"正在访问: {url}")
            driver.get(url)

            # 等待页面主体加载
            WebDriverWait(driver, 15).until(EC.presence_of_element_located((By.TAG_NAME, "body")))

            # 1. 尝试点击 Continue 按钮
            continue_selectors = [
                "//button[contains(text(), 'Continue')]",
                "//button[contains(text(), '继续')]",
                "//a[contains(text(), 'Continue')]",
                "//*[@id='continueBtn']"
            ]
            clicked = False
            for selector in continue_selectors:
                try:
                    btn = WebDriverWait(driver, 5).until(EC.element_to_be_clickable((By.XPATH, selector)))
                    btn.click()
                    logger.info("已点击 Continue 按钮")
                    clicked = True
                    break
                except:
                    pass

            # 2. 等待页面更新（可能跳转到广告页或验证码页）
            time.sleep(5)

            # 3. 检查是否需要处理验证码（简单检测 hCaptcha）
            page_source = driver.page_source
            if 'hcaptcha' in page_source.lower() or 'recaptcha' in page_source.lower():
                logger.info("检测到验证码，进入验证码处理流程")
                # 如果配置了 2Captcha，自动解决；否则进入半自动模式
                # if solver:
                #     captcha_token = self._solve_hcaptcha(driver.current_url)
                #     if captcha_token:
                #         driver.execute_script(f"document.getElementById('hcaptcha-response').value = '{captcha_token}';")
                #         submit_btn = driver.find_element(By.XPATH, "//button[@type='submit']")
                #         submit_btn.click()
                #         time.sleep(5)
                #     else:
                #         return {'success': False, 'error': '自动验证码解决失败'}
                # else:
                # 半自动模式：等待用户手动完成验证码
                if not HEADLESS:
                    input("⚠️ 请在浏览器中手动完成验证码，完成后按回车键继续...")
                else:
                    # 无头模式下无法手动，直接失败
                    return {'success': False, 'error': '需要验证码，请稍后重试或配置 2Captcha'}

            # 4. 等待最终结果页面，提取卡密
            time.sleep(8)  # 给页面足够时间加载卡密
            final_text = driver.page_source
            key = self._extract_key_from_text(final_text)
            if key:
                logger.info(f"成功提取卡密: {key}")
                return {'success': True, 'result': key}
            else:
                # 再等5秒试试
                time.sleep(5)
                final_text = driver.page_source
                key = self._extract_key_from_text(final_text)
                if key:
                    return {'success': True, 'result': key}
                return {'success': False, 'error': '未能提取到卡密，请检查链接是否有效'}

        except Exception as e:
            logger.error(f"Selenium 处理异常: {e}")
            return {'success': False, 'error': f'处理异常: {str(e)}'}
        finally:
            if driver:
                driver.quit()

    def _extract_key_from_text(self, text: str) -> Optional[str]:
        """从文本中提取卡密"""
        # 匹配 FREE_ 后跟32位十六进制
        match = re.search(r'FREE_?[a-fA-F0-9]{32}', text, re.IGNORECASE)
        if match:
            key = match.group(0)
            if not key.startswith('FREE_'):
                key = 'FREE_' + key[4:]
            return key
        # 匹配纯32位十六进制
        match = re.search(r'\b[a-fA-F0-9]{32}\b', text)
        if match:
            return f"FREE_{match.group(0)}"
        # 匹配20-40位字母数字
        match = re.search(r'\b[A-Za-z0-9]{20,40}\b', text)
        if match:
            return match.group(0)
        return None

    # 如果需要自动解决验证码，取消注释并实现以下方法
    # def _solve_hcaptcha(self, page_url: str) -> Optional[str]:
    #     try:
    #         site_key = "69a3b3f1-9884-4e4f-b381-2843c64d955d"  # bypass.vip 的 sitekey，其他网站需抓包获取
    #         result = solver.hcaptcha(sitekey=site_key, pageurl=page_url)
    #         return result['code']
    #     except Exception as e:
    #         logger.error(f"2Captcha 失败: {e}")
    #         return None
