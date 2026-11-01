from astrbot.core.message.components import At
from astrbot.core.platform.astr_message_event import AstrMessageEvent
from astrbot.core.star.filter.command import CommandFilter
from astrbot.core.star.filter.command_group import CommandGroupFilter
from astrbot.core.star.star_handler import star_handlers_registry

# 机器人账号区间（闭区间）
BOT_RANGES: list[tuple[int, int]] = [
    (3328144510, 3328144510),
    (2854196301, 2854216399),
    (66600000, 66600000),
    (3889000000, 3889999999),
    (4010000000, 4019999999),
]


def is_qqbot(uid: int | str) -> bool:
    """
    判断是否为 qqbot 账号

    :param uid: 用户 ID（支持 str / int）
    :return: 是否为 bot
    """
    try:
        uid = int(uid)
    except (TypeError, ValueError):
        return False

    for start, end in BOT_RANGES:
        if start <= uid <= end:
            return True
    return False


def get_all_commands() -> list[str]:
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


def get_ats(
    event: AstrMessageEvent,
    noself: bool = True,
    block_ids: list[str] | None = None,
    skip_first_seg: bool = True,
):
    """
    获取被at者们的id列表(@增强版)
    Args:
        event: 消息事件对象
        noself: 是否排除自己
        block_ids: 要排除的id列表
        skip_first_seg: 是否跳过第一个消息段（默认为True）
    """
    segs = event.get_messages()
    segs = segs[1:] if skip_first_seg else segs
    ats = {str(seg.qq) for seg in segs if isinstance(seg, At)}
    ats.update(
        arg[1:]
        for arg in event.message_str.split()
        if arg.startswith("@") and arg[1:].isdigit()
    )
    if noself:
        ats.discard(event.get_self_id())
    if block_ids:
        ats.difference_update(block_ids)
    return list(ats)
