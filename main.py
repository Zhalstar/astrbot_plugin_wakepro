import time

from astrbot.api.event import filter
from astrbot.api.star import Context, Star
from astrbot.core.config.astrbot_config import AstrBotConfig
from astrbot.core.message.components import At, Plain
from astrbot.core.platform.astr_message_event import AstrMessageEvent
from astrbot.core.star.filter.command import CommandFilter
from astrbot.core.star.filter.command_group import CommandGroupFilter
from astrbot.core.star.star_handler import star_handlers_registry

from .core.config import PluginConfig
from .core.model import (
    MemberState,
    StateManager,
    WakeContext,
)
from .core.pipeline import Pipeline


class WakePlugin(Star):
    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        self.cfg = PluginConfig(config, context)
        self.commands = self._get_all_commands()
        self.pipeline = Pipeline(self.cfg)

    @staticmethod
    def _get_all_commands() -> list[str]:
        """遍历所有注册的处理器获取所有命令"""
        commands = []
        for handler in star_handlers_registry:
            for fl in handler.event_filters:
                if isinstance(fl, CommandFilter):
                    commands.append(fl.command_name)
                    break
                elif isinstance(fl, CommandGroupFilter):
                    commands.append(fl.group_name)
                    break
        return commands

    @filter.event_message_type(filter.EventMessageType.ALL, priority=99999)
    async def on_group_msg(self, event: AstrMessageEvent):
        """收到消息后"""
        umo = event.unified_msg_origin
        gid = event.get_group_id()
        uid = event.get_sender_id()
        bid = event.get_self_id()

        if uid == bid:
            return

        if any(x in self.cfg.global_blacklist for x in (umo, uid, gid)):
            event.stop_event()
            return

        chain = event.get_messages()
        plains = [seg.text for seg in chain if isinstance(seg, Plain)]
        plain = " ".join(plains).strip()
        first_arg = event.message_str.split(" ", 1)[0]
        cmd = first_arg if first_arg in self.commands else None

        group = StateManager.get_group(gid) if gid else None
        if group and uid not in group.members:
            group.members[uid] = MemberState(uid=uid)

        ctx = WakeContext(
            event=event,
            chain=chain,
            plain=plain,
            cmd=cmd,
            is_admin=event.is_admin(),
            umo=umo,
            gid=gid,
            uid=uid,
            bid=bid,
            group=group,
            member=group.members[uid] if group else None,
            now=time.time(),
        )
        await self.pipeline.run(ctx)

    @filter.on_decorating_result(priority=20)
    async def on_decorating_result(self, event: AstrMessageEvent):
        """消息发送前"""
        uid = event.get_sender_id()
        if uid:
            await StateManager.clear_pending_request(
                StateManager.get_pending_key(event.unified_msg_origin, uid),
                event=event,
            )

        gid: str = event.get_group_id()
        result = event.get_result()

        if not gid or not uid or not result:
            return

        group = StateManager.get_group(gid)
        group.bot_msgs.append(result.get_plain_text())

        member = group.members.get(uid)
        if member:
            member.last_reply = time.time()


    def _extract_target_id(self, event: AstrMessageEvent, target_id: str | None = None) -> str | None:
        """从参数或消息中的 At 组件提取目标 ID"""
        for seg in event.message_obj.message:
            if isinstance(seg, At) and seg.qq and seg.qq != "all":
                return str(seg.qq).strip()
        if target_id:
            cleaned = target_id.strip()
            if cleaned.startswith("@"):
                cleaned = cleaned[1:].strip()
            if cleaned:
                return cleaned
        return None

    @filter.command("屏蔽唤醒")
    async def cmd_block_wake(self, event: AstrMessageEvent, target_id: str | None = None):
        """屏蔽指定用户的唤醒"""
        uid = self._extract_target_id(event, target_id)
        if not uid:
            yield event.plain_result("请指定要屏蔽的用户ID或At目标用户，例如：/屏蔽唤醒 123456 或 /屏蔽唤醒 @某人")
            return

        if self.cfg.add_block_user(uid):
            yield event.plain_result(f"已将用户 {uid} 加入屏蔽唤醒列表")
        else:
            yield event.plain_result(f"用户 {uid} 已在屏蔽唤醒列表中")

    @filter.command("允许唤醒")
    async def cmd_allow_wake(self, event: AstrMessageEvent, target_id: str | None = None):
        """从屏蔽唤醒列表中移除指定用户"""
        uid = self._extract_target_id(event, target_id)
        if not uid:
            yield event.plain_result("请指定要允许的用户ID或At目标用户，例如：/允许唤醒 123456 或 /允许唤醒 @某人")
            return

        if self.cfg.remove_block_user(uid):
            yield event.plain_result(f"已将用户 {uid} 从屏蔽唤醒列表中移除")
        else:
            yield event.plain_result(f"用户 {uid} 不在屏蔽唤醒列表中")
