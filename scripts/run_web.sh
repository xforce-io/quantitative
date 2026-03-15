#!/bin/bash

# 获取脚本所在目录的上一级目录（即项目根目录）
PROJECT_ROOT="$( cd "$( dirname "${BASH_SOURCE[0]}" )/.." && pwd )"
PID_FILE="${PROJECT_ROOT}/.web.pid"
LOG_FILE="${PROJECT_ROOT}/logs/web.log"
PORT=8501

# 添加项目根目录到 PYTHONPATH
export PYTHONPATH="${PROJECT_ROOT}:${PYTHONPATH}"

# 确保 logs 目录存在
mkdir -p "${PROJECT_ROOT}/logs"

# 获取当前运行的 PID
get_pid() {
    if [ -f "$PID_FILE" ]; then
        local pid=$(cat "$PID_FILE")
        if ps -p "$pid" > /dev/null 2>&1; then
            echo "$pid"
            return 0
        fi
    fi
    local port_pid
    port_pid=$(lsof -tiTCP:"$PORT" -sTCP:LISTEN 2>/dev/null | head -n 1)
    if [ -n "$port_pid" ]; then
        echo "$port_pid" > "$PID_FILE"
        echo "$port_pid"
        return 0
    fi
    echo ""
    return 1
}

# 启动服务
start() {
    local pid=$(get_pid)
    if [ -n "$pid" ]; then
        echo "⚠️  Web platform is already running (PID: $pid)"
        return 1
    fi

    echo "🚀 Starting Quantitative Trading Web Platform..."
    echo "📂 Project Root: ${PROJECT_ROOT}"

    # 检查 streamlit 是否安装
    if ! command -v streamlit &> /dev/null; then
        echo "⚠️  Streamlit NOT found. Installing..."
        uv pip install streamlit
    fi

    # 后台运行 streamlit (禁用自动打开浏览器)
    nohup streamlit run "${PROJECT_ROOT}/web/Home.py" --server.headless=true > "$LOG_FILE" 2>&1 &

    # 等待端口监听并回填真实 PID
    local count=0
    local new_pid=""
    while [ $count -lt 20 ]; do
        sleep 1
        new_pid=$(lsof -tiTCP:"$PORT" -sTCP:LISTEN 2>/dev/null | head -n 1)
        if [ -n "$new_pid" ]; then
            echo "$new_pid" > "$PID_FILE"
            break
        fi
        count=$((count + 1))
    done

    if [ -n "$new_pid" ] && ps -p "$new_pid" > /dev/null 2>&1; then
        echo "✅ Web platform started (PID: $new_pid)"
        echo "📝 Log file: $LOG_FILE"
        echo "🌐 Access at: http://localhost:8501"
    else
        echo "❌ Failed to start web platform. Check log: $LOG_FILE"
        rm -f "$PID_FILE"
        return 1
    fi
}

# 停止服务
stop() {
    local pid=$(get_pid)
    if [ -z "$pid" ]; then
        echo "⚠️  Web platform is not running"
        return 1
    fi

    echo "🛑 Stopping web platform (PID: $pid)..."
    kill "$pid" 2>/dev/null

    # 等待进程退出
    local count=0
    while ps -p "$pid" > /dev/null 2>&1 && [ $count -lt 10 ]; do
        sleep 1
        count=$((count + 1))
    done

    if ps -p "$pid" > /dev/null 2>&1; then
        echo "⚠️  Force killing..."
        kill -9 "$pid" 2>/dev/null
    fi

    local port_pid
    port_pid=$(lsof -tiTCP:"$PORT" -sTCP:LISTEN 2>/dev/null | head -n 1)
    if [ -n "$port_pid" ]; then
        kill "$port_pid" 2>/dev/null
        sleep 1
        if ps -p "$port_pid" > /dev/null 2>&1; then
            kill -9 "$port_pid" 2>/dev/null
        fi
    fi

    rm -f "$PID_FILE"
    echo "✅ Web platform stopped"
}

# 重启服务
restart() {
    echo "🔄 Restarting web platform..."
    stop
    sleep 1
    start
}

# 查看状态
status() {
    local pid=$(get_pid)
    if [ -n "$pid" ]; then
        echo "✅ Web platform is running (PID: $pid)"
        echo "🌐 Access at: http://localhost:8501"
    else
        echo "⚪ Web platform is not running"
    fi
}

# 查看日志
logs() {
    if [ -f "$LOG_FILE" ]; then
        tail -f "$LOG_FILE"
    else
        echo "⚠️  Log file not found: $LOG_FILE"
    fi
}

# 主入口
case "${1:-start}" in
    start)
        start
        ;;
    stop)
        stop
        ;;
    restart)
        restart
        ;;
    status)
        status
        ;;
    logs)
        logs
        ;;
    *)
        echo "Usage: $0 {start|stop|restart|status|logs}"
        echo ""
        echo "Commands:"
        echo "  start   - Start web platform in background"
        echo "  stop    - Stop web platform"
        echo "  restart - Restart web platform"
        echo "  status  - Show running status"
        echo "  logs    - Tail log file"
        exit 1
        ;;
esac
