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
from .core.utils import get_ats


class WakePlugin(Star):
    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        self.cfg = PluginConfig(config, context)
        self.pipeline = Pipeline(self.cfg)

    async def initialize(self) -> None:
        """Initialize the wake pipeline and its optional Jev client."""
        await self.pipeline.initialize()

    async def terminate(self) -> None:
        """Release resources held by the wake pipeline."""
        await self.pipeline.terminate()

    @staticmethod
    def _get_all_commands() -> list[str]:
        """Read command names and aliases from the current handler registry.

        Returns:
            Complete command names, including command group paths and aliases.
        """
        commands = []
        for handler in star_handlers_registry:
            for fl in handler.event_filters:
                if isinstance(fl, (CommandFilter, CommandGroupFilter)):
                    commands.extend(fl.get_complete_command_names())
                    break
        return commands

    @filter.event_message_type(filter.EventMessageType.ALL, priority=99999)
    async def on_group_msg(self, event: AstrMessageEvent):
        """收到消息后"""
        umo = event.unified_msg_origin
        gid = event.get_group_id()
        uid = event.get_sender_id()
        bid = event.get_self_id()
        platform_id = str(event.get_platform_id() or "")

        if uid == bid:
            return

        chain = event.get_messages()
        plains = [seg.text for seg in chain if isinstance(seg, Plain)]
        plain = " ".join(plains).strip()
        # AstrBot has already removed the wake prefix before dispatching handlers.
        message_str = " ".join(event.message_str.split())
        cmd = next(
            (
                name.split(" ", 1)[0]
                for name in self._get_all_commands()
                if message_str == name or message_str.startswith(f"{name} ")
            ),
            None,
        )

        group = (
            StateManager.get_group(gid, platform_id=platform_id, bot_id=str(bid))
            if gid
            else None
        )
        if group and uid not in group.members:
            group.members[uid] = MemberState(uid=uid)
        if group and not cmd:
            message_id = str(getattr(event.message_obj, "message_id", "") or "")
            group.history.append(
                {
                    "message_id": message_id or f"{uid}:{time.time_ns()}",
                    "sender_id": str(uid),
                    "sender_name": event.get_sender_name() or "",
                    "text": plain,
                    "time": time.time(),
                    "is_bot": False,
                    "bot_id": str(bid),
                }
            )

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

        group = StateManager.get_group(
            gid,
            platform_id=str(event.get_platform_id() or ""),
            bot_id=str(event.get_self_id()),
        )
        group.bot_msgs.append(result.get_plain_text())
        group.history.append(
            {
                "message_id": f"bot:{event.get_self_id()}:{time.time_ns()}",
                "sender_id": str(event.get_self_id()),
                "sender_name": "",
                "text": result.get_plain_text(),
                "time": time.time(),
                "is_bot": True,
                "bot_id": str(event.get_self_id()),
            }
        )

        member = group.members.get(uid)
        if (
            member
            and member.can_prolong
            and event.get_extra("wakepro_prolong_reply", False)
        ):
            member.last_reply = time.time()

    @filter.command("屏蔽用户", alias={"屏蔽唤醒"})
    async def cmd_block_wake(self, event: AstrMessageEvent, target_id: str = ""):
        """屏蔽用户 @用户A @用户B 或QQ号"""
        uids = get_ats(event)
        if not uids:
            blocked_users = self.cfg.block.block_users
            msg = (
                "当前屏蔽的用户：\n" + "\n".join(blocked_users)
                if blocked_users
                else "当前没有屏蔽任何用户，请用命令“屏蔽用户 @用户”添加"
            )
            yield event.plain_result(msg)
            return
        results = []
        for uid in uids:
            if self.cfg.add_block_user(uid):
                results.append(f"已屏蔽用户：{uid}")
            else:
                results.append(f"用户屏蔽中：{uid}")
        yield event.plain_result("\n".join(results))

    @filter.command("解除屏蔽")
    async def cmd_allow_wake(self, event: AstrMessageEvent, target_id: str = ""):
        """解除屏蔽 @用户A @用户B 或QQ号"""
        uids = list(
            dict.fromkeys(
                str(seg.qq).strip()
                for seg in event.get_messages()
                if (
                    isinstance(seg, At)
                    and seg.qq
                    and str(seg.qq).strip() not in ("", "all", str(event.get_self_id()))
                )
            )
        )
        uid = target_id.strip().removeprefix("@").strip()
        if not uids and uid and uid not in ("all", str(event.get_self_id())):
            uids.append(uid)
        if not uids:
            blocked_users = self.cfg.block.block_users
            yield event.plain_result(
                "当前可解除屏蔽的用户：\n" + "\n".join(blocked_users)
                if blocked_users
                else "当前没有屏蔽任何用户"
            )
            return
        results = []
        for uid in uids:
            if self.cfg.remove_block_user(uid):
                results.append(f"已解除屏蔽：{uid}")
            else:
                results.append(f"用户未被屏蔽：{uid}")
        yield event.plain_result("\n".join(results))
