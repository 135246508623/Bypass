import re
import httpx
from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, register
from astrbot.api import logger

# 从 filter 模块导入 EventMessageType 枚举，用于指定消息类型过滤
from astrbot.api.event.filter import EventMessageType

@register("bypass_helper", "阿玛特拉斯", "自动绕过广告/卡密链接", "1.0.0")
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
        self.api_url = "https://api.izen.lol/bypass"
        self.timeout = 15.0
        self.group_last_call = {}

    @filter.event_message_type(EventMessageType.GROUP)
    async def on_group_message(self, event: AstrMessageEvent):
        """监听所有群聊消息"""
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
        result = await self.bypass(target_url)
        if result['success']:
            yield event.plain_result(f"✅ 绕过成功！\n结果: {result['result']}")
        else:
            yield event.plain_result(f"❌ 绕过失败: {result['error']}")

    async def bypass(self, url: str):
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.get(self.api_url, params={'url': url})
                resp.raise_for_status()
                data = resp.json()
                if data.get('success') and data.get('result'):
                    return {'success': True, 'result': data['result']}
                return {'success': False, 'error': data.get('error', '未知错误')}
        except Exception as e:
            return {'success': False, 'error': str(e)}
