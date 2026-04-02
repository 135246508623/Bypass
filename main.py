import re
import httpx
from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, register
from astrbot.api import logger
from astrbot.api.event.filter import EventMessageType

@register("bypass_helper", "YourName", "自动绕过广告/卡密链接", "1.0.0")
class BypassPlugin(Star):
    def __init__(self, context: Context):
        super().__init__(context)
        self.patterns = [
            r'auth\.platorelay\.com',
            r'auth\.platoboost\.(?:com|net|click|app|me)',
            r'deltaios-executor\.com',
            r'linkvertise\.com',
            r'work\.ink',
            r'loot-link\.com',
            r'rekonise\.com',
        ]
        # 多个候选 API 端点（按可能性排序）
        self.api_endpoints = [
            "https://api.izen.lol/bypass",
            "https://api.izen.lol/v1/bypass",
            "https://api.izen.lol/bypassv2",
            "https://api.izen.lol/api/bypass",
            "https://zen-api.bypass.lol/bypass",
            "https://bypass.city/api/bypass",
        ]
        self.timeout = 15.0
        self.group_last_call = {}

    @filter.event_message_type(EventMessageType.GROUP_MESSAGE)
    async def on_group_message(self, event: AstrMessageEvent):
        message = event.message_str
        urls = re.findall(r'https?://[^\s]+', message)
        if not urls:
            return
        target_url = None
        for url in urls:
            for pattern in self.patterns:
                if re.search(pattern, url, re.I):
                    target_url = url
                    break
            if target_url:
                break
        if not target_url:
            return

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
        """依次尝试多个 API 端点"""
        for endpoint in self.api_endpoints:
            try:
                async with httpx.AsyncClient(timeout=self.timeout) as client:
                    resp = await client.get(endpoint, params={'url': url})
                    if resp.status_code == 200:
                        data = resp.json()
                        if data.get('success') and data.get('result'):
                            return {'success': True, 'result': data['result']}
                        elif data.get('key'):
                            return {'success': True, 'result': data['key']}
                    # 状态码不是200或返回格式不对，继续尝试下一个端点
                logger.warning(f"端点 {endpoint} 返回非200或无效数据")
            except Exception as e:
                logger.warning(f"端点 {endpoint} 请求失败: {e}")
                continue
        return {'success': False, 'error': '所有 API 端点均不可用，请稍后重试'}

    async def bypass(self, url: str):
        return await self.try_bypass(url)
