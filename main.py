import re
import httpx
from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, register
from astrbot.api import logger
from astrbot.api.event.filter import EventMessageType

@register("astrbot_plugin_bypass", "YourName", "HTTP直连解卡机器人（增强版）", "5.5.0")
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
        # 多个 User-Agent 轮换
        self.user_agents = [
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        ]

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
        for ua in self.user_agents:
            headers = {
                'User-Agent': ua,
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
                'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
                'Accept-Encoding': 'gzip, deflate, br',
                'Connection': 'keep-alive',
                'Upgrade-Insecure-Requests': '1',
                'Sec-Fetch-Dest': 'document',
                'Sec-Fetch-Mode': 'navigate',
                'Sec-Fetch-Site': 'none',
                'Sec-Fetch-User': '?1',
                'Cache-Control': 'max-age=0',
            }
            try:
                async with httpx.AsyncClient(timeout=15, follow_redirects=True, http2=True) as client:
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
                        # 尝试匹配纯32位十六进制
                        match = re.search(r'\b[a-fA-F0-9]{32}\b', text)
                        if match:
                            return {'success': True, 'result': f"FREE_{match.group(0)}"}
                    else:
                        logger.warning(f"HTTP {resp.status_code} with UA {ua[:50]}...")
            except Exception as e:
                logger.warning(f"Request with UA {ua[:50]}... failed: {e}")
                continue
        return {'success': False, 'error': '所有请求均未找到卡密。这可能是因为目标网站需要执行 JavaScript，请使用浏览器方案或手动获取。'}
