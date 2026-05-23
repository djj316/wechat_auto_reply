"""
Amadeus 智能 AI 助手 v2.0 - 主程序入口

多平台、多模态智能 AI 助手。支持大模型驱动的角色扮演对话、
Web 管理面板、Live2D 交互等多种能力。

支持的 LLM 提供商:
  - doubao   : 豆包（火山引擎）
  - openai   : OpenAI（GPT 系列）
  - deepseek : DeepSeek
  - qwen     : 通义千问（阿里云）
  - moonshot : 月之暗面（Kimi）
  - glm      : 智谱（GLM）

使用说明:
    python main.py                          # 使用默认配置启动（微信自动回复）
    python main.py --config my_config.json  # 使用自定义配置
    python main.py --no-llm                 # 禁用大模型回复，使用预设消息
    python main.py --provider deepseek      # 切换提供商
    python main.py --web-admin              # 启动 Web 管理面板
"""

import sys
import io
import os
import time
import signal
import argparse
from datetime import datetime
from typing import Optional

# 解决 Windows 终端 GBK 编码问题
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

# 加载 .env 文件（如果存在）
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from config import load_config, validate_config, Config
from auto_reply import process_auto_reply, reset_tracking, set_llm_client
from llm_client import LLMClient
from wechat_monitor import find_wechat_window


# 全局运行标志
_running = True

# 全局 LLM 客户端
_llm_client: Optional[LLMClient] = None


def signal_handler(signum, frame):
    """信号处理函数 - 优雅退出"""
    global _running
    print("\n[主程序] 收到停止信号，正在退出...")
    _running = False


def print_banner():
    """打印程序启动横幅"""
    banner = """
╔══════════════════════════════════════════╗
║         Amadeus 智能 AI 助手 v2.0         ║
║    多平台 · 大模型驱动 · 角色扮演         ║
╚══════════════════════════════════════════╝
"""
    print(banner)


def print_status(config: Config, reply_count: int, total_checks: int):
    """
    打印运行状态

    Args:
        config: 配置对象
        reply_count: 已回复次数
        total_checks: 总检查次数
    """
    global _llm_client

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    in_time = "🟢 在时间段内" if _is_in_time_range_now(config) else "🔴 不在时间段内"
    llm_status = _llm_client.get_status_string() if _llm_client else "🔴 LLM: 未启用"

    print(f"\r[{now}] {in_time} | "
          f"已检查: {total_checks} 次 | "
          f"已回复: {reply_count} 次 | "
          f"联系人: {len(config.contacts)} 个 | "
          f"间隔: {config.check_interval}s | "
          f"{llm_status}",
          end="", flush=True)


def _is_in_time_range_now(config: Config) -> bool:
    """检查当前是否在配置的时间段内（内部辅助函数）"""
    from auto_reply import is_in_time_range
    return is_in_time_range(config.time_ranges)


def parse_args():
    """解析命令行参数"""
    parser = argparse.ArgumentParser(
        description="Amadeus 智能 AI 助手 v2.0 - 多平台 · 大模型驱动 · 角色扮演"
    )
    parser.add_argument(
        "--config", "-c",
        type=str,
        default=None,
        help="配置文件路径（默认: 同目录下的 config.json）"
    )
    parser.add_argument(
        "--interval", "-i",
        type=float,
        default=None,
        help="消息检测间隔（秒，覆盖配置文件中的设置）"
    )
    parser.add_argument(
        "--no-llm",
        action="store_true",
        help="禁用大模型回复，使用预设消息"
    )
    parser.add_argument(
        "--provider", "-p",
        type=str,
        default=None,
        help="大模型提供商（覆盖配置文件，如 doubao/openai/deepseek/qwen/moonshot/glm）"
    )
    parser.add_argument(
        "--character", "-ch",
        type=str,
        default=None,
        help="角色名称（覆盖配置文件中的设置，如 kurisu）"
    )
    parser.add_argument(
        "--list-providers",
        action="store_true",
        help="列出所有支持的 LLM 提供商"
    )
    parser.add_argument(
        "--web-admin", "-w",
        action="store_true",
        help="同时启动 Web 管理面板（默认地址: http://127.0.0.1:5000）"
    )
    parser.add_argument(
        "--web-host",
        type=str,
        default="127.0.0.1",
        help="Web 管理面板监听地址（默认: 127.0.0.1）"
    )
    parser.add_argument(
        "--web-port",
        type=int,
        default=5000,
        help="Web 管理面板监听端口（默认: 5000）"
    )
    return parser.parse_args()


def init_llm_client(config: Config, args) -> Optional[LLMClient]:
    """
    初始化大模型客户端

    根据配置的 provider 自动读取对应的环境变量中的 API Key。

    Args:
        config: 配置对象
        args: 命令行参数

    Returns:
        LLMClient 实例，未启用则返回 None
    """
    # 命令行参数 --no-llm 覆盖配置
    if args.no_llm:
        print("[主程序] 已通过命令行参数禁用大模型回复")
        return None

    if not config.llm.enabled:
        print("[主程序] 大模型回复未启用（可在 config.json 中设置 llm.enabled=true）")
        return None

    # 命令行参数覆盖提供商和角色
    provider = args.provider or config.llm.provider
    character = args.character or config.llm.character

    # API Key 由 LLMClient 内部根据 provider 自动从对应环境变量读取
    # 不需要在这里手动获取

    print()
    print("[主程序] 🤖 正在初始化大模型...")
    client = LLMClient(
        provider=provider,
        api_endpoint=config.llm.api_endpoint or None,
        model=config.llm.model or None,
        max_tokens=config.llm.max_tokens,
        temperature=config.llm.temperature,
        character=character,
        enable_context=config.llm.enable_context,
        context_window=config.llm.context_window,
    )

    if not client.is_ready:
        print("[主程序] ❌ 大模型初始化失败，将使用预设消息")
        return None

    return client


def main():
    """主函数"""
    global _running, _llm_client

    # 保存原始 stdout，防止 Flask 接管后 print 崩溃
    import sys as _sys
    _original_stdout = _sys.stdout

    def _safe_print(*args, **kwargs):
        """安全的 print，避免 Flask 接管 stdout 后崩溃"""
        try:
            print(*args, **kwargs)
        except (ValueError, OSError):
            try:
                # 尝试恢复到原始 stdout
                if _sys.stdout is not _original_stdout:
                    _sys.stdout = _original_stdout
                print(*args, **kwargs)
            except Exception:
                pass

    def _restore_stdout():
        """恢复 stdout 到原始状态"""
        try:
            if _sys.stdout is not _original_stdout:
                _sys.stdout = _original_stdout
        except Exception:
            pass

    # 注册信号处理
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    # 打印横幅
    print_banner()

    # 解析命令行参数
    args = parse_args()

    # --list-providers 参数：列出所有支持的提供商
    if args.list_providers:
        from llm_client import get_provider_names, get_provider_display_name, PROVIDER_CONFIGS
        print("[主程序] 📋 支持的 LLM 提供商:")
        print()
        for name in get_provider_names():
            cfg = PROVIDER_CONFIGS[name]
            print(f"  {name:12s} - {cfg['name']}")
            print(f"              默认模型: {cfg['default_model']}")
            print(f"              环境变量: {cfg['env_key']}")
            print(f"              文档地址: {cfg['doc_url']}")
            print()
        return

    # 加载配置
    config = load_config(args.config)

    # 命令行参数覆盖配置
    if args.interval is not None and args.interval > 0:
        config.check_interval = args.interval
    if args.provider is not None:
        config.llm.provider = args.provider

    # 验证配置
    errors = validate_config(config)
    if errors:
        print("[主程序] ❌ 配置验证失败:")
        for err in errors:
            print(f"  - {err}")
        print("[主程序] 请修改配置文件后重试")
        sys.exit(1)

    # 打印配置信息
    print(f"[主程序] 配置文件: {args.config or 'config.json'}")
    contact_display = []
    for c in config.contacts:
        if c.relation:
            contact_display.append(f"{c.name}({c.relation})")
        else:
            contact_display.append(c.name)
    print(f"[主程序] 监控联系人: {', '.join(contact_display)}")
    print(f"[主程序] 工作时间段: ", end="")
    for tr in config.time_ranges:
        print(f"{tr['start']}-{tr['end']}  ", end="")
    print()
    print(f"[主程序] 回复模式: {'大模型(LLM)' if config.llm.enabled else '预设消息'}")
    if config.llm.enabled:
        from llm_client import get_provider_display_name
        print(f"[主程序] LLM 提供商: {get_provider_display_name(config.llm.provider)} ({config.llm.provider})")
    print(f"[主程序] 检测间隔: {config.check_interval} 秒")
    print(f"[主程序] 日志文件: {config.log_file}")
    print()

    # 初始化大模型客户端
    _llm_client = init_llm_client(config, args)
    set_llm_client(_llm_client)
    print()

    # ============================================================
    # Web 管理面板（可选）
    # ============================================================
    if args.web_admin:
        try:
            from web.app import create_app, set_llm_client as web_set_llm, set_live2d_llm_client as web_set_live2d_llm
            from llm_client import LLMClient
            import threading

            web_app = create_app(args.config)
            web_set_llm(_llm_client)

            # 创建 Live2D 专用 LLM 客户端（使用独立的 Amadeus 对话提示词）
            if _llm_client is not None and _llm_client.is_ready:
                try:
                    live2d_client = LLMClient(
                        provider=config.llm.provider,
                        api_endpoint=config.llm.api_endpoint or None,
                        model=config.llm.model or None,
                        max_tokens=config.llm.max_tokens,
                        temperature=config.llm.temperature,
                        character="kurisu_live2d",
                        enable_context=config.llm.enable_context,
                        context_window=20,  # Live2D 对话保留更多上下文（20轮）
                    )
                    if live2d_client.is_ready:
                        web_set_live2d_llm(live2d_client)
                        print("[主程序] ✅ Live2D 对话专用客户端已初始化（使用 Amadeus 自然对话风格）")
                    else:
                        print("[主程序] ⚠️ Live2D 对话客户端初始化失败，将使用主客户端")
                except Exception as e:
                    print(f"[主程序] ⚠️ Live2D 对话客户端创建失败: {e}")
            else:
                print("[主程序] ⚠️ 主 LLM 客户端未就绪，Live2D 对话将不可用")

            def _run_web():
                # 将 Flask 的 stdout/stderr 重定向到 os.devnull，
                # 防止 Flask 关闭主线程的 stdout 导致 print 崩溃
                import io as _io
                try:
                    old_stdout = _sys.stdout
                    old_stderr = _sys.stderr
                    _sys.stdout = _sys.stderr  # Flask 输出到 stderr
                    web_app.run(
                        host=args.web_host,
                        port=args.web_port,
                        debug=False,
                        use_reloader=False,
                    )
                finally:
                    _sys.stdout = old_stdout
                    _sys.stderr = old_stderr

            web_thread = threading.Thread(
                target=_run_web,
                daemon=True,
            )
            web_thread.start()
            # 给 Flask 一点时间启动
            time.sleep(0.5)
            # Flask 启动后立即恢复 stdout，防止后续 print 崩溃
            _restore_stdout()
            _safe_print(f"[主程序] 🌐 Web 管理面板: http://{args.web_host}:{args.web_port}")
            _safe_print(f"[主程序]    在浏览器中打开以上地址管理配置和查看状态")
            _safe_print()
        except ImportError as e:
            _safe_print(f"[主程序] ⚠️ Web 管理面板加载失败: {e}")
            _safe_print(f"[主程序]    请确保已安装 Flask: pip install flask")
        except Exception as e:
            _safe_print(f"[主程序] ⚠️ Web 管理面板启动失败: {e}")

    # 如果启用了 Web 管理面板，默认不启动微信聊天模块，等待用户在 Web 上点击"启动"
    if args.web_admin:
        _running = False
        # 同步 Web 面板的运行状态
        try:
            from web.app import set_running as web_set_running
            web_set_running(False)
        except Exception:
            pass
        _safe_print("[主程序] 🔴 微信聊天模块默认已暂停，请在 Web 管理面板中点击「启动」按钮开启")
        _safe_print()
    else:
        # 非 Web 模式：正常启动微信聊天模块
        # 检查微信是否运行
        _safe_print("[主程序] 正在检查微信客户端...")
        wechat_window = find_wechat_window()
        if not wechat_window:
            _safe_print("[主程序] ⚠️ 未检测到微信窗口，请确保微信已登录并打开")
            _safe_print("[主程序] 程序将继续运行，等待微信启动...")
        else:
            _safe_print("[主程序] ✅ 微信客户端已检测到")

        _safe_print()
        _safe_print("[主程序] 🟢 开始运行... (按 Ctrl+C 停止)")
        _safe_print()

    # 运行统计
    reply_count = 0
    total_checks = 0
    last_status_time = 0

    # 主循环
    while True:
        # Web 模式下通过 web.app.is_running() 检查运行状态（支持 Web 面板控制）
        if args.web_admin:
            try:
                from web.app import is_running as web_is_running
                web_running = web_is_running()
                if not web_running:
                    time.sleep(1)
                    continue
            except Exception as e:
                _safe_print(f"[主程序] ⚠️ is_running() 异常: {e}")
                if not _running:
                    time.sleep(1)
                    continue
        else:
            if not _running:
                time.sleep(1)
                continue
        try:
            _safe_print(f"[主程序] 🔄 开始检测... (total_checks={total_checks})")
            # 获取选中的联系人（Web 模式下只检测用户勾选的联系人）
            selected = None
            if args.web_admin:
                try:
                    from web.app import get_selected_contacts
                    sel_dict = get_selected_contacts()
                    if sel_dict:
                        # 只取值为 True 的联系人名称
                        selected = {name for name, enabled in sel_dict.items() if enabled}
                    _safe_print(f"[主程序] 📋 选中联系人: {selected}")
                except Exception as e:
                    _safe_print(f"[主程序] ⚠️ get_selected_contacts 异常: {e}")

            # 执行自动回复检查（只处理选中的联系人）
            count = process_auto_reply(config, selected)
            reply_count += count
            total_checks += 1
            _safe_print(f"[主程序] ✅ 检测完成, count={count}, total_checks={total_checks}")

            # 更新 Web 面板统计
            if args.web_admin:
                try:
                    from web.app import update_stats
                    update_stats(reply_count, total_checks)
                except Exception as e:
                    _safe_print(f"[主程序] ⚠️ update_stats 异常: {e}")

            # 每秒更新一次状态显示
            current_time = time.time()
            if current_time - last_status_time >= 1.0:
                print_status(config, reply_count, total_checks)
                last_status_time = current_time

            # 等待指定间隔
            time.sleep(config.check_interval)

        except KeyboardInterrupt:
            break
        except Exception as e:
            _safe_print(f"\n[主程序] ⚠️ 运行异常: {e}")
            time.sleep(5)  # 异常时等待 5 秒后重试
            continue

    # 退出统计
    _safe_print("\n")
    _safe_print("═" * 50)
    _safe_print("[主程序] 📊 运行统计")
    _safe_print(f"  总检查次数: {total_checks}")
    _safe_print(f"  总回复次数: {reply_count}")
    contact_display = []
    for c in config.contacts:
        if c.relation:
            contact_display.append(f"{c.name}({c.relation})")
        else:
            contact_display.append(c.name)
    _safe_print(f"  监控联系人: {', '.join(contact_display)}")
    if _llm_client:
        _safe_print(f"  大模型状态: {_llm_client.get_status_string()}")
    _safe_print("[主程序] 👋 已退出")


if __name__ == "__main__":
    main()
