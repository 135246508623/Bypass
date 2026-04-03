import re
import httpx
from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, register
from astrbot.api import logger
from astrbot.api.event.filter import EventMessageType

@register("bypass_helper", "YourName", "自动绕过广告/卡密链接（增强版）", "1.1.0")
class BypassPlugin(Star):
    def __init__(self, context: Context):
        super().__init__(context)
        # 支持的链接域名（用于校验）
        self.patterns = [
            r'auth\.platorelay\.com',
            r'auth\.platoboost\.(?:com|net|click|app|me)',
            r'deltaios-executor\.com',
            r'linkvertise\.com',
            r'work\.ink',
            r'loot-link\.com',
            r'rekonise\.com',
        ]
        # 尽可能多的候选 API 端点（结合 bypass.vip 源码及常见服务）
        self.api_endpoints = [
            # 从 bypass.vip 网页源码推测的端点
            "https://bypass.vip/api/bypass",
            "https://bypass.vip/bypass",
            "https://api.bypass.vip/bypass",
            # 其他公开服务
            "https://bypassunlock.com/api/bypass",
            "https://api.bypass.city/v1/bypass",
            "https://api.izen.lol/bypass",
            "https://api.izen.lol/v1/bypass",
            "https://api.izen.lol/bypassv2",
            "https://zen-api.bypass.lol/bypass",
        ]
        self.timeout = 15.0
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

        yield event.plain_result("正在处理，请稍候...")
        result = await self.try_bypass(target_url)
        if result['success']:
            yield event.plain_result(f"✅ 绕过成功！\n结果: {result['result']}")
        else:
            yield event.plain_result(f"❌ 绕过失败: {result['error']}")

    async def try_bypass(self, url: str):
        """尝试所有端点，并从响应中暴力提取卡密"""
        # 伪造更真实的请求头，减少被拒绝的概率
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "application/json, text/plain, */*",
            "Referer": "https://bypass.vip/",
            "Origin": "https://bypass.vip",
        }

        for endpoint in self.api_endpoints:
            try:
                async with httpx.AsyncClient(timeout=self.timeout, headers=headers) as client:
                    # 尝试 GET 请求
                    resp = await client.get(endpoint, params={'url': url})
                    if resp.status_code == 200:
                        text = resp.text
                        # 1. 尝试 JSON 解析
                        try:
                            data = resp.json()
                            if data.get('success') and data.get('result'):
                                return {'success': True, 'result': data['result']}
                            if data.get('key'):
                                return {'success': True, 'result': data['key']}
                        except:
                            pass
                        # 2. 直接匹配 FREE_ 卡密（你的格式）
                        match = re.search(r'FREE_[a-fA-F0-9]{32}', text, re.IGNORECASE)
                        if match:
                            return {'success': True, 'result': match.group(0)}
                        # 3. 匹配纯 32 位十六进制，自动加上 FREE_ 前缀
                        match2 = re.search(r'\b[a-fA-F0-9]{32}\b', text)
                        if match2:
                            return {'success': True, 'result': f"FREE_{match2.group(0)}"}
                        # 4. 匹配其他常见卡密格式（如大写字母数字组合）
                        match3 = re.search(r'\b[A-Z0-9]{20,40}\b', text)
                        if match3:
                            return {'success': True, 'result': match3.group(0)}
                        # 5. 如果响应是纯文本链接，直接返回
                        if text.startswith('http://') or text.startswith('https://'):
                            return {'success': True, 'result': text.strip()}
                        # 否则记录警告
                        logger.warning(f"端点 {endpoint} 返回未识别内容: {text[:200]}")
                    else:
                        logger.warning(f"端点 {endpoint} 状态码 {resp.status_code}")
            except Exception as e:
                logger.warning(f"端点 {endpoint} 异常: {e}")
                continue
        return {'success': False, 'error': '所有 API 均不可用，请稍后重试或使用用户脚本'}
