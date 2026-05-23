"""
Web 管理面板 - Flask 后端 API

提供 RESTful API 用于：
- 读取/更新配置
- 查看回复日志
- 查看运行状态
- 测试 LLM 回复
- 控制自动回复启停

启动方式（独立运行）：
    python web_admin/app.py

或通过 main.py 集成启动：
    python main.py --web-admin
"""

import os
import sys
import json
import time
import threading
from datetime import datetime
from typing import Optional

from flask import Flask, jsonify, request, render_template, send_from_directory

# 添加项目根目录到 sys.path
_project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from config import load_config, save_config, validate_config, Config, ContactConfig
from llm_client import LLMClient, get_provider_names, get_provider_display_name, PROVIDER_CONFIGS

app = Flask(__name__)

# ============================================================
# 全局状态
# ============================================================

# 运行状态
_running = True
_reply_count = 0
_total_checks = 0
_start_time = time.time()

# LLM 客户端（由主程序注入，或独立运行时创建）
_llm_client: Optional[LLMClient] = None

# 配置路径
_config_path: Optional[str] = None


# ============================================================
# 辅助函数
# ============================================================

def _get_config() -> Config:
    """获取当前配置"""
    global _config_path
    return load_config(_config_path)


def _read_log_file(log_path: str, max_lines: int = 200) -> list:
    """读取日志文件，返回最近 max_lines 行"""
    try:
        abs_path = os.path.join(_project_root, log_path) if not os.path.isabs(log_path) else log_path
        if not os.path.exists(abs_path):
            return []
        with open(abs_path, "r", encoding="utf-8") as f:
            lines = f.readlines()
        # 取最近 max_lines 行
        return [line.strip() for line in lines[-max_lines:]]
    except Exception as e:
        return [f"[错误] 读取日志失败: {e}"]


def _format_uptime() -> str:
    """格式化运行时间"""
    elapsed = int(time.time() - _start_time)
    hours, remainder = divmod(elapsed, 3600)
    minutes, seconds = divmod(remainder, 60)
    if hours > 0:
        return f"{hours}小时{minutes}分{seconds}秒"
    elif minutes > 0:
        return f"{minutes}分{seconds}秒"
    return f"{seconds}秒"


# ============================================================
# API 路由
# ============================================================

@app.route("/")
def index():
    """管理面板首页"""
    return render_template("index.html")


@app.route("/api/status")
def api_status():
    """获取运行状态"""
    config = _get_config()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # 检查是否在时间段内
    from auto_reply import is_in_time_range
    in_time = is_in_time_range(config.time_ranges)

    # LLM 状态
    llm_status = "未启用"
    if _llm_client and _llm_client.is_ready:
        llm_status = f"{get_provider_display_name(_llm_client.provider)} ({_llm_client.model})"
    elif config.llm.enabled:
        llm_status = "已配置但未就绪"

    return jsonify({
        "running": _running,
        "current_time": now,
        "in_time_range": in_time,
        "uptime": _format_uptime(),
        "reply_count": _reply_count,
        "total_checks": _total_checks,
        "contact_count": len(config.contacts),
        "check_interval": config.check_interval,
        "llm_enabled": config.llm.enabled,
        "llm_status": llm_status,
        "llm_ready": _llm_client is not None and _llm_client.is_ready,
    })


@app.route("/api/config", methods=["GET"])
def api_get_config():
    """获取完整配置"""
    try:
        config = _get_config()
        return jsonify({
            "success": True,
            "config": {
                "enabled": config.enabled,
                "check_interval": config.check_interval,
                "contacts": [
                    {
                        "name": c.name,
                        "relation": c.relation,
                        "personalization": dict(c.personalization),
                    }
                    for c in config.contacts
                ],
                "time_ranges": config.time_ranges,
                "reply_message": config.reply_message,
                "log_file": config.log_file,
                "sticker_path": config.sticker_path,
                "llm": {
                    "enabled": config.llm.enabled,
                    "provider": config.llm.provider,
                    "api_endpoint": config.llm.api_endpoint,
                    "model": config.llm.model,
                    "max_tokens": config.llm.max_tokens,
                    "temperature": config.llm.temperature,
                    "character": config.llm.character,
                    "enable_context": config.llm.enable_context,
                    "context_window": config.llm.context_window,
                },
            },
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/config", methods=["PUT"])
def api_update_config():
    """更新配置"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({"success": False, "error": "请求体为空"}), 400

        config = _get_config()

        # 更新基本字段
        if "enabled" in data:
            config.enabled = bool(data["enabled"])
        if "check_interval" in data:
            config.check_interval = float(data["check_interval"])
        if "reply_message" in data:
            config.reply_message = str(data["reply_message"])
        if "log_file" in data:
            config.log_file = str(data["log_file"])
        if "sticker_path" in data:
            config.sticker_path = str(data["sticker_path"])

        # 更新时间段
        if "time_ranges" in data:
            config.time_ranges = data["time_ranges"]

        # 更新联系人
        if "contacts" in data:
            config.contacts = [
                ContactConfig(
                    name=c["name"],
                    relation=c.get("relation", ""),
                    personalization=c.get("personalization", {}),
                )
                for c in data["contacts"]
            ]

        # 更新 LLM 配置
        if "llm" in data:
            llm_data = data["llm"]
            config.llm.enabled = bool(llm_data.get("enabled", config.llm.enabled))
            config.llm.provider = str(llm_data.get("provider", config.llm.provider))
            config.llm.api_endpoint = str(llm_data.get("api_endpoint", config.llm.api_endpoint))
            config.llm.model = str(llm_data.get("model", config.llm.model))
            config.llm.max_tokens = int(llm_data.get("max_tokens", config.llm.max_tokens))
            config.llm.temperature = float(llm_data.get("temperature", config.llm.temperature))
            config.llm.character = str(llm_data.get("character", config.llm.character))
            config.llm.enable_context = bool(llm_data.get("enable_context", config.llm.enable_context))
            config.llm.context_window = int(llm_data.get("context_window", config.llm.context_window))

        # 验证配置
        errors = validate_config(config)
        if errors:
            return jsonify({"success": False, "errors": errors}), 400

        # 保存配置
        if save_config(config, _config_path):
            return jsonify({"success": True, "message": "配置已保存"})
        else:
            return jsonify({"success": False, "error": "保存配置失败"}), 500

    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/logs")
def api_get_logs():
    """获取回复日志"""
    try:
        config = _get_config()
        max_lines = request.args.get("max_lines", 200, type=int)
        lines = _read_log_file(config.log_file, max_lines)
        return jsonify({
            "success": True,
            "log_file": config.log_file,
            "total_lines": len(lines),
            "lines": lines,
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/providers")
def api_get_providers():
    """获取支持的 LLM 提供商列表"""
    providers = []
    for key, cfg in PROVIDER_CONFIGS.items():
        providers.append({
            "id": key,
            "name": cfg["name"],
            "default_model": cfg["default_model"],
            "env_key": cfg["env_key"],
            "doc_url": cfg["doc_url"],
        })
    return jsonify({"success": True, "providers": providers})


@app.route("/api/llm/test", methods=["POST"])
def api_llm_test():
    """测试 LLM 回复"""
    try:
        data = request.get_json()
        message = data.get("message", "你好") if data else "你好"
        contact_name = data.get("contact_name", "测试")
        contact_relation = data.get("contact_relation", "")

        if not _llm_client or not _llm_client.is_ready:
            return jsonify({
                "success": False,
                "error": "LLM 客户端未就绪，请检查 API Key 配置",
            }), 400

        success, reply = _llm_client.chat(contact_name, message, contact_relation)
        if success:
            return jsonify({
                "success": True,
                "reply": reply,
                "contact_name": contact_name,
            })
        else:
            return jsonify({
                "success": False,
                "error": "LLM 回复生成失败",
            }), 500

    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/llm/reset", methods=["POST"])
def api_llm_reset():
    """重置 LLM 对话历史"""
    try:
        data = request.get_json()
        contact_name = data.get("contact_name") if data else None

        if _llm_client:
            _llm_client.reset_conversation(contact_name)
            if contact_name:
                return jsonify({"success": True, "message": f"已重置 [{contact_name}] 的对话历史"})
            else:
                return jsonify({"success": True, "message": "已重置所有对话历史"})
        return jsonify({"success": False, "error": "LLM 客户端未初始化"}), 400
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/control/start", methods=["POST"])
def api_control_start():
    """启动自动回复"""
    global _running
    _running = True
    return jsonify({"success": True, "message": "自动回复已启动"})


@app.route("/api/control/stop", methods=["POST"])
def api_control_stop():
    """停止自动回复"""
    global _running
    _running = False
    return jsonify({"success": True, "message": "自动回复已停止"})


@app.route("/api/control/restart", methods=["POST"])
def api_control_restart():
    """重启自动回复（重置追踪状态）"""
    global _running, _reply_count, _total_checks
    try:
        from auto_reply import reset_tracking
        reset_tracking()
        _reply_count = 0
        _total_checks = 0
        _running = True
        return jsonify({"success": True, "message": "已重置追踪状态并启动"})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


# ============================================================
# 状态更新接口（供主程序调用）
# ============================================================

def update_stats(reply_count: int, total_checks: int):
    """更新统计信息（由主程序线程调用）"""
    global _reply_count, _total_checks
    _reply_count = reply_count
    _total_checks = total_checks


def set_llm_client(client: Optional[LLMClient]):
    """设置 LLM 客户端实例（由主程序注入）"""
    global _llm_client
    _llm_client = client


def is_running() -> bool:
    """检查是否应继续运行（供主程序读取）"""
    return _running


# ============================================================
# 启动入口
# ============================================================

def create_app(config_path: Optional[str] = None) -> Flask:
    """创建 Flask 应用实例"""
    global _config_path
    _config_path = config_path
    return app


def run_web_admin(host: str = "127.0.0.1", port: int = 5000,
                  config_path: Optional[str] = None,
                  llm_client: Optional[LLMClient] = None,
                  debug: bool = False):
    """
    启动 Web 管理面板（独立运行或由主程序调用）

    Args:
        host: 监听地址
        port: 监听端口
        config_path: 配置文件路径
        llm_client: LLM 客户端实例
        debug: 是否启用调试模式
    """
    global _config_path, _llm_client
    _config_path = config_path
    _llm_client = llm_client

    print(f"[Web] 🌐 Web 管理面板启动: http://{host}:{port}")
    print(f"[Web]    配置文件: {config_path or '默认'}")
    print(f"[Web]    LLM 客户端: {'已注入' if llm_client else '未注入'}")
    print(f"[Web]    按 Ctrl+C 停止")

    app.run(host=host, port=port, debug=debug, use_reloader=False)


if __name__ == "__main__":
    # 独立运行模式
    import argparse
    parser = argparse.ArgumentParser(description="Web 管理面板")
    parser.add_argument("--host", default="127.0.0.1", help="监听地址")
    parser.add_argument("--port", type=int, default=5000, help="监听端口")
    parser.add_argument("--config", help="配置文件路径")
    parser.add_argument("--debug", action="store_true", help="调试模式")
    args = parser.parse_args()

    run_web_admin(
        host=args.host,
        port=args.port,
        config_path=args.config,
        debug=args.debug,
    )
