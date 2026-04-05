import re
import httpx
from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, register
from astrbot.api import logger
from astrbot.api.event.filter import EventMessageType

@register("astrbot_plugin_bypass", "YourName", "HTTP直连解卡机器人（快速稳定）", "5.2.0")
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
        result = await self.try_http(target_url)
        if result['success']:
            yield event.plain_result(f"✅ 成功！\n{result['result']}")
        else:
            yield event.plain_result(f"❌ 失败: {result['error']}")

    async def try_http(self, url: str):
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'zh-CN,zh;q=0.8,en-US;q=0.5,en;q=0.3',
            'Connection': 'keep-alive',
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
                    # 尝试无下划线格式
                    match = re.search(r'FREE[a-fA-F0-9]{32}', text, re.IGNORECASE)
                    if match:
                        key = match.group(0)
                        if not key.startswith('FREE_'):
                            key = 'FREE_' + key[4:]
                        return {'success': True, 'result': key}
                    # 检测成功白名单页面
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
