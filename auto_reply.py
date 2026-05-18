"""
自动回复引擎模块 - 时间段判断、联系人匹配、发送回复

核心逻辑：
- 追踪每个联系人的最后一条消息内容
- 当检测到新消息时（消息内容变化），自动回复
- 支持大模型生成回复（角色扮演）和预设消息两种模式
- 对方每发一条消息，就回复一条
"""

import time
import datetime
from typing import List, Dict, Optional

import uiautomation as auto

from config import Config
from llm_client import LLMClient
from wechat_monitor import (
    find_wechat_window,
    activate_chat,
    get_chat_input_edit,
    bring_window_to_front,
    get_last_message_text,
)


# 记录每个联系人最后一条消息的内容，用于检测新消息
# 格式: {contact_name: last_message_text}
_last_messages: Dict[str, str] = {}

# 大模型客户端实例（由主程序初始化）
_llm_client: Optional[LLMClient] = None


def set_llm_client(client: Optional[LLMClient]):
    """
    设置大模型客户端实例

    Args:
        client: LLMClient 实例，None 表示不使用大模型
    """
    global _llm_client
    _llm_client = client


def is_in_time_range(time_ranges: List[dict]) -> bool:
    """
    判断当前时间是否在配置的时间段内

    Args:
        time_ranges: 时间段列表，格式 [{"start": "HH:MM", "end": "HH:MM"}, ...]

    Returns:
        是否在时间段内
    """
    if not time_ranges:
        return False

    now = datetime.datetime.now()
    current_time = now.strftime("%H:%M")

    for tr in time_ranges:
        try:
            start = tr["start"]
            end = tr["end"]
            if start <= current_time <= end:
                return True
        except (KeyError, TypeError):
            continue

    return False


def should_reply(contact_name: str, config: Config) -> bool:
    """
    判断是否应对指定联系人进行自动回复

    Args:
        contact_name: 联系人名称
        config: 配置对象

    Returns:
        是否应该回复
    """
    # 检查总开关
    if not config.enabled:
        return False

    # 检查是否在时间段内
    if not is_in_time_range(config.time_ranges):
        return False

    # 检查联系人是否在监控列表中
    if contact_name not in config.contacts:
        return False

    return True


def has_new_message(wechat_window, contact_name: str) -> bool:
    """
    检测指定联系人是否有新消息

    通过对比当前最后一条消息与之前记录的最后一条消息来判断。

    Args:
        wechat_window: 微信主窗口控件
        contact_name: 联系人名称

    Returns:
        是否有新消息
    """
    global _last_messages

    try:
        # 激活联系人聊天窗口以获取最新消息
        if not activate_chat(wechat_window, contact_name):
            return False

        time.sleep(0.3)

        # 获取当前最后一条消息
        current_last = get_last_message_text(wechat_window)
        if current_last is None:
            return False

        # 获取之前记录的最后一条消息
        previous_last = _last_messages.get(contact_name)

        if previous_last is None:
            # 首次检测，记录当前消息但不触发回复
            _last_messages[contact_name] = current_last
            print(f"[检测] 首次记录 [{contact_name}] 的最后消息: {current_last[:30]}...")
            return False

        if current_last != previous_last:
            # 消息发生了变化，说明有新消息
            _last_messages[contact_name] = current_last
            print(f"[检测] 🔔 [{contact_name}] 发来新消息: {current_last[:30]}...")
            return True

        return False

    except Exception as e:
        print(f"[检测] 检测新消息失败 ({contact_name}): {e}")
        return False


def _generate_llm_reply(contact_name: str, user_message: str) -> Optional[str]:
    """
    使用大模型生成回复

    Args:
        contact_name: 联系人名称
        user_message: 用户发送的消息内容

    Returns:
        生成的回复文本，失败返回 None
    """
    global _llm_client

    if _llm_client is None or not _llm_client.is_ready:
        return None

    print(f"[LLM] 正在为 [{contact_name}] 生成回复...")
    success, reply = _llm_client.chat(contact_name, user_message)

    if success:
        print(f"[LLM] ✅ 生成回复成功: {reply[:50]}...")
        return reply
    else:
        print(f"[LLM] ❌ 生成回复失败")
        return None


def send_reply(
    wechat_window,
    contact_name: str,
    message: str
) -> bool:
    """
    向指定联系人发送回复消息

    Args:
        wechat_window: 微信主窗口控件
        contact_name: 联系人名称
        message: 回复消息内容

    Returns:
        是否发送成功
    """
    global _last_messages

    try:
        # 将微信窗口置于前台
        if not bring_window_to_front(wechat_window):
            print(f"[回复] 无法将微信窗口置于前台")
            return False

        time.sleep(0.3)

        # 激活联系人聊天窗口
        if not activate_chat(wechat_window, contact_name):
            print(f"[回复] 无法激活联系人聊天窗口: {contact_name}")
            return False

        time.sleep(0.5)

        # 获取输入框
        edit = get_chat_input_edit(wechat_window)
        if not edit:
            print(f"[回复] 无法获取聊天输入框")
            return False

        # 点击输入框获取焦点
        edit.Click()
        time.sleep(0.2)

        # 清空输入框（全选 + 删除）
        edit.SendKeys("{Ctrl}a")
        time.sleep(0.1)
        edit.SendKeys("{Delete}")
        time.sleep(0.1)

        # 输入回复消息
        # 使用 SendKeys 逐行输入，处理多行消息
        lines = message.split("\n")
        for i, line in enumerate(lines):
            edit.SendKeys(line)
            if i < len(lines) - 1:
                # 不是最后一行，按 Shift+Enter 换行
                edit.SendKeys("{Shift}{Enter}")
                time.sleep(0.1)
            else:
                time.sleep(0.1)

        time.sleep(0.2)

        # 按 Enter 发送
        edit.SendKeys("{Enter}")
        time.sleep(0.5)

        # 发送成功后，更新追踪记录为刚刚发送的消息内容
        # 这样下次检测时不会把刚发的回复当作新消息
        _last_messages[contact_name] = message
        print(f"[回复] ✅ 已向 [{contact_name}] 发送自动回复")
        return True

    except Exception as e:
        print(f"[回复] ❌ 发送回复失败 ({contact_name}): {e}")
        return False


def log_reply(contact_name: str, log_file: str, is_llm: bool = False):
    """
    记录回复日志

    Args:
        contact_name: 联系人名称
        log_file: 日志文件路径
        is_llm: 是否为大模型生成的回复
    """
    try:
        now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        mode = "LLM" if is_llm else "预设"
        log_entry = f"[{now}] [{mode}] 已向 [{contact_name}] 发送自动回复\n"

        with open(log_file, "a", encoding="utf-8") as f:
            f.write(log_entry)
    except Exception as e:
        print(f"[回复] 写入日志失败: {e}")


def process_auto_reply(config: Config) -> int:
    """
    执行一次自动回复检查和处理

    遍历配置中的联系人，检测是否有新消息，有则自动回复。
    优先使用大模型生成回复，失败时降级到预设消息。

    Args:
        config: 配置对象

    Returns:
        本次处理的回复数量
    """
    # 如果不在时间段内，跳过
    if not is_in_time_range(config.time_ranges):
        return 0

    # 查找微信窗口
    wechat_window = find_wechat_window()
    if not wechat_window:
        return 0

    reply_count = 0

    # 遍历配置中的联系人，检测新消息
    for contact_name in config.contacts:
        # 判断是否需要回复
        if not should_reply(contact_name, config):
            continue

        # 检测是否有新消息
        if has_new_message(wechat_window, contact_name):
            print(f"[回复] 检测到 [{contact_name}] 的新消息，准备回复")

            # 获取对方发送的消息内容（用于大模型上下文）
            user_message = _last_messages.get(contact_name, "")

            # 决定回复内容
            reply_message = config.reply_message  # 默认使用预设消息
            is_llm_reply = False

            # 如果启用了大模型，尝试生成回复
            if config.llm.enabled and _llm_client and _llm_client.is_ready:
                llm_reply = _generate_llm_reply(contact_name, user_message)
                if llm_reply:
                    reply_message = llm_reply
                    is_llm_reply = True
                else:
                    print(f"[回复] 大模型回复失败，降级到预设消息")

            # 发送回复
            success = send_reply(
                wechat_window,
                contact_name,
                reply_message
            )

            if success:
                log_reply(contact_name, config.log_file, is_llm=is_llm_reply)
                reply_count += 1

    return reply_count


def reset_tracking():
    """重置消息追踪记录（退出时间段时调用）"""
    global _last_messages
    _last_messages.clear()
    # 同时重置 LLM 对话历史
    if _llm_client is not None:
        _llm_client.reset_conversation()
    print("[检测] 消息追踪记录已重置")
