"""
Amadeus Web 管理服务 - Flask 后端 API

提供 Web 管理面板的后端 API 服务，包括：
- 状态监控
- 配置管理（读取/保存）
- LLM 对话测试
- 日志查看
- Live2D 控制
- 运行控制

Usage:
    python -m web.app              # 独立运行
    python main.py --web-admin     # 随主程序运行
"""

import os
import sys
import json
import time
import threading
from datetime import datetime, timedelta
from typing import Optional, List, Dict

from flask import Flask, request, jsonify, render_template

# 添加项目根目录到路径
_project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from config import load_config, save_config, validate_config, Config
from llm_client import LLMClient, get_provider_names, get_provider_display_name, PROVIDER_CONFIGS

# ============================================================
# 全局状态
# ============================================================
_start_time = time.time()
_reply_count = 0
_total_checks = 0
_llm_client: Optional[LLMClient] = None
_live2d_llm_client: Optional[LLMClient] = None
_running = True
_config_path: Optional[str] = None

# 联系人选中状态（用于手动选择要检测的联系人）
# 格式: {contact_name: True/False}
_selected_contacts: Dict[str, bool] = {}


def create_app(config_path: Optional[str] = None) -> Flask:
    """
    创建 Flask 应用实例

    Args:
        config_path: 配置文件路径

    Returns:
        Flask 应用
    """
    global _config_path
    _config_path = config_path

    app = Flask(
        __name__,
        template_folder=os.path.join(os.path.dirname(__file__), "templates"),
        static_folder=os.path.join(os.path.dirname(__file__), "static"),
    )

    # 开发模式下自动重载模板，修改 HTML 后刷新即可生效，无需重启服务器
    app.config["TEMPLATES_AUTO_RELOAD"] = True

    # ============================================================
    # 主页面
    # ============================================================
    @app.route("/")
    def index():
        return render_template("index.html")

    # ============================================================
    # API: 状态
    # ============================================================
    @app.route("/api/status")
    def api_status():
        """获取运行状态"""
        global _reply_count, _total_checks, _start_time, _running

        config = load_config(_config_path)
        uptime_seconds = int(time.time() - _start_time)
        uptime_str = str(timedelta(seconds=uptime_seconds))

        # 检查是否在时间段内
        from auto_reply import is_in_time_range
        in_time = is_in_time_range(config.time_ranges)

        llm_ready = _llm_client is not None and _llm_client.is_ready
        llm_status = _llm_client.get_status_string() if _llm_client else "未启用"

        return jsonify({
            "success": True,
            "running": _running,
            "uptime": uptime_str,
            "current_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "reply_count": _reply_count,
            "total_checks": _total_checks,
            "contact_count": len(config.contacts),
            "in_time_range": in_time,
            "llm_ready": llm_ready,
            "llm_enabled": config.llm.enabled,
            "llm_status": llm_status,
        })

    # ============================================================
    # API: 配置
    # ============================================================
    @app.route("/api/config", methods=["GET"])
    def api_get_config():
        """获取当前配置"""
        try:
            config = load_config(_config_path)
            from dataclasses import asdict
            data = asdict(config)
            return jsonify({"success": True, "config": data})
        except Exception as e:
            return jsonify({"success": False, "error": str(e)})

    @app.route("/api/config", methods=["PUT"])
    def api_update_config():
        """更新配置"""
        try:
            data = request.get_json()
            if not data:
                return jsonify({"success": False, "error": "请求数据为空"})

            # 构建新的 Config 对象
            from config import LLMConfig, ContactConfig, _parse_contacts

            llm_data = data.get("llm", {})
            llm_config = LLMConfig(
                enabled=llm_data.get("enabled", False),
                provider=llm_data.get("provider", "doubao"),
                api_endpoint=llm_data.get("api_endpoint", ""),
                model=llm_data.get("model", ""),
                max_tokens=llm_data.get("max_tokens", 500),
                temperature=llm_data.get("temperature", 0.8),
                character=llm_data.get("character", "kurisu"),
                enable_context=llm_data.get("enable_context", True),
                context_window=llm_data.get("context_window", 10),
            )

            raw_contacts = data.get("contacts", [])
            contacts = _parse_contacts(raw_contacts)

            config = Config(
                enabled=data.get("enabled", True),
                check_interval=data.get("check_interval", 2.0),
                contacts=contacts,
                time_ranges=data.get("time_ranges", []),
                reply_message=data.get("reply_message", ""),
                log_file=data.get("log_file", "reply_log.txt"),
                llm=llm_config,
                sticker_path=data.get("sticker_path", ""),
            )

            # 验证配置
            errors = validate_config(config)
            if errors:
                return jsonify({"success": False, "errors": errors})

            # 保存配置
            ok = save_config(config, _config_path)
            if ok:
                return jsonify({"success": True, "message": "配置已保存"})
            else:
                return jsonify({"success": False, "error": "保存配置失败"})

        except Exception as e:
            return jsonify({"success": False, "error": str(e)})

    # ============================================================
    # API: 日志
    # ============================================================
    @app.route("/api/logs")
    def api_logs():
        """获取回复日志"""
        try:
            config = load_config(_config_path)
            log_file = config.log_file

            max_lines = request.args.get("max_lines", 300, type=int)

            if not os.path.exists(log_file):
                return jsonify({"success": True, "lines": [], "total": 0})

            with open(log_file, "r", encoding="utf-8") as f:
                all_lines = f.readlines()

            # 取最后 N 行
            lines = all_lines[-max_lines:] if len(all_lines) > max_lines else all_lines
            # 去除换行符
            lines = [l.rstrip("\n\r") for l in lines]

            return jsonify({
                "success": True,
                "lines": lines,
                "total": len(all_lines),
            })
        except Exception as e:
            return jsonify({"success": False, "error": str(e)})

    # ============================================================
    # API: 提供商列表
    # ============================================================
    @app.route("/api/providers")
    def api_providers():
        """获取所有支持的 LLM 提供商"""
        providers = []
        for name in get_provider_names():
            cfg = PROVIDER_CONFIGS[name]
            providers.append({
                "id": name,
                "name": cfg["name"],
                "default_model": cfg["default_model"],
                "env_key": cfg["env_key"],
            })
        return jsonify({"success": True, "providers": providers})

    # ============================================================
    # API: LLM 测试
    # ============================================================
    @app.route("/api/llm/test", methods=["POST"])
    def api_llm_test():
        """测试 LLM 回复"""
        global _llm_client

        if _llm_client is None or not _llm_client.is_ready:
            return jsonify({
                "success": False,
                "error": "LLM 客户端未就绪，请检查 API Key 配置",
            })

        try:
            data = request.get_json()
            message = data.get("message", "")
            contact_name = data.get("contact_name", "测试")
            contact_relation = data.get("contact_relation", "")

            if not message.strip():
                return jsonify({"success": False, "error": "消息内容不能为空"})

            success, reply = _llm_client.chat(
                contact_name, message, contact_relation
            )

            if success:
                return jsonify({"success": True, "reply": reply})
            else:
                return jsonify({"success": False, "error": "LLM 回复生成失败"})

        except Exception as e:
            return jsonify({"success": False, "error": str(e)})

    @app.route("/api/llm/reset", methods=["POST"])
    def api_llm_reset():
        """重置 LLM 对话历史"""
        global _llm_client

        if _llm_client is None:
            return jsonify({"success": False, "error": "LLM 客户端未初始化"})

        try:
            data = request.get_json() or {}
            contact_name = data.get("contact_name")
            _llm_client.reset_conversation(contact_name)
            return jsonify({"success": True, "message": "对话历史已重置"})
        except Exception as e:
            return jsonify({"success": False, "error": str(e)})

    @app.route("/api/llm/live2d_chat", methods=["POST"])
    def api_llm_live2d_chat():
        """Live2D 对话（使用独立的 Amadeus 提示词）"""
        global _live2d_llm_client

        if _live2d_llm_client is None or not _live2d_llm_client.is_ready:
            # 如果 Live2D 专用客户端未就绪，尝试使用主客户端
            if _llm_client is not None and _llm_client.is_ready:
                client = _llm_client
            else:
                return jsonify({
                    "success": False,
                    "error": "LLM 客户端未就绪，请检查 API Key 配置",
                })
        else:
            client = _live2d_llm_client

        try:
            data = request.get_json()
            message = data.get("message", "")
            contact_name = data.get("contact_name", "User")

            if not message.strip():
                return jsonify({"success": False, "error": "消息内容不能为空"})

            success, reply = client.chat(
                contact_name, message, "朋友"
            )

            if success:
                return jsonify({"success": True, "reply": reply})
            else:
                return jsonify({"success": False, "error": "LLM 回复生成失败"})

        except Exception as e:
            return jsonify({"success": False, "error": str(e)})

    # ============================================================
    # API: 控制
    # ============================================================
    @app.route("/api/control/start", methods=["POST"])
    def api_control_start():
        """启动自动回复"""
        set_running(True)
        return jsonify({"success": True, "message": "自动回复已启动"})

    @app.route("/api/control/stop", methods=["POST"])
    def api_control_stop():
        """停止自动回复"""
        set_running(False)
        return jsonify({"success": True, "message": "自动回复已停止"})

    @app.route("/api/control/restart", methods=["POST"])
    def api_control_restart():
        """重置追踪状态"""
        try:
            from auto_reply import reset_tracking
            reset_tracking()
            return jsonify({"success": True, "message": "追踪状态已重置"})
        except Exception as e:
            return jsonify({"success": False, "error": str(e)})

    @app.route("/api/contacts/selection", methods=["GET"])
    def api_get_contact_selection():
        """获取联系人选中状态"""
        global _selected_contacts
        return jsonify({
            "success": True,
            "selected": _selected_contacts,
        })

    @app.route("/api/contacts/selection", methods=["POST"])
    def api_set_contact_selection():
        """设置联系人选中状态"""
        global _selected_contacts
        try:
            data = request.get_json()
            if not data or "selected" not in data:
                return jsonify({"success": False, "error": "缺少 selected 字段"})
            _selected_contacts = data["selected"]
            return jsonify({"success": True, "message": "联系人选中状态已更新"})
        except Exception as e:
            return jsonify({"success": False, "error": str(e)})

    # ============================================================
    # API: Live2D
    # ============================================================
    @app.route("/api/live2d/status")
    def api_live2d_status():
        """获取 Live2D 状态"""
        static_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")
        model_json = os.path.join(static_dir, "live2d", "amadeusV1.model3.json")
        has_model = os.path.isfile(model_json)

        return jsonify({
            "success": True,
            "loaded": has_model,
            "has_model": has_model,
            "model_name": "牧濑红莉栖 (Kurisu)" if has_model else None,
        })

    @app.route("/api/live2d/model_info")
    def api_live2d_model_info():
        """获取 Live2D 模型信息"""
        static_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")
        model_json = os.path.join(static_dir, "live2d", "amadeusV1.model3.json")

        if not os.path.isfile(model_json):
            return jsonify({
                "success": False,
                "error": "模型文件不存在",
            })

        try:
            with open(model_json, "r", encoding="utf-8") as f:
                model_info = json.load(f)
            # 统计动作和表情
            motions_dir = os.path.join(static_dir, "live2d", "motions")
            motion_count = 0
            if os.path.isdir(motions_dir):
                motion_count = len([f for f in os.listdir(motions_dir) if f.endswith('.json')])
            return jsonify({
                "success": True,
                "name": "牧濑红莉栖 (Kurisu)",
                "expressions": model_info.get("FileReferences", {}).get("Expressions", None),
                "motions": motion_count,
                "model_info": model_info,
            })
        except Exception as e:
            return jsonify({
                "success": False,
                "error": f"读取模型信息失败: {e}",
            })

    # ============================================================
    # 静态文件路由: Live2D 模型文件
    # ============================================================
    from flask import send_from_directory

    @app.route("/static/live2d/<path:filename>")
    def serve_live2d_files(filename):
        """提供 Live2D 模型静态文件"""
        live2d_dir = os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            "static", "live2d"
        )
        return send_from_directory(live2d_dir, filename)

    @app.route("/static/lib/<path:filename>")
    def serve_lib_files(filename):
        """提供 Live2D 库文件"""
        lib_dir = os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            "static", "lib"
        )
        return send_from_directory(lib_dir, filename)

    return app


# ============================================================
# 外部接口（供 main.py 调用）
# ============================================================

def update_stats(reply_count: int, total_checks: int):
    """
    更新统计信息（由主程序调用）

    Args:
        reply_count: 回复次数
        total_checks: 检查次数
    """
    global _reply_count, _total_checks
    _reply_count = reply_count
    _total_checks = total_checks


def set_llm_client(client: Optional[LLMClient]):
    """
    设置 LLM 客户端实例（由主程序调用）

    Args:
        client: LLMClient 实例
    """
    global _llm_client
    _llm_client = client


def set_live2d_llm_client(client: Optional[LLMClient]):
    """
    设置 Live2D 专用 LLM 客户端实例（由主程序调用）

    Args:
        client: LLMClient 实例（使用 kurisu_live2d 角色）
    """
    global _live2d_llm_client
    _live2d_llm_client = client


def get_selected_contacts() -> Dict[str, bool]:
    """获取联系人选中状态（供 main.py 调用）"""
    global _selected_contacts
    return _selected_contacts


def is_running() -> bool:
    """获取运行状态"""
    global _running
    return _running


def set_running(state: bool):
    """设置运行状态（同时同步到 main 模块）"""
    global _running
    _running = state
    # 同步修改 main.py 的 _running 变量
    try:
        import main as main_module
        main_module._running = state
    except Exception:
        pass


# ============================================================
# 独立运行入口
# ============================================================

def run_web_admin(config_path: Optional[str] = None,
                  host: str = "127.0.0.1",
                  port: int = 5000):
    """
    独立运行 Web 管理面板

    Args:
        config_path: 配置文件路径
        host: 监听地址
        port: 监听端口
    """
    app = create_app(config_path)
    print(f"[Amadeus] 🌐 Web 管理面板启动: http://{host}:{port}")
    print(f"[Amadeus]    按 Ctrl+C 停止")
    app.run(host=host, port=port, debug=False)


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Amadeus Web 管理面板")
    parser.add_argument("--config", "-c", type=str, default=None,
                        help="配置文件路径")
    parser.add_argument("--host", type=str, default="127.0.0.1",
                        help="监听地址")
    parser.add_argument("--port", "-p", type=int, default=5000,
                        help="监听端口")
    args = parser.parse_args()

    run_web_admin(args.config, args.host, args.port)
