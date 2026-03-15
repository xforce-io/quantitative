#!/bin/bash

# FastAPI 服务启动脚本
# 用法: 
#   ./scripts/run_api.sh        # 启动服务 (前台)
#   ./scripts/run_api.sh dev    # 开发模式 (热重载)
#   ./scripts/run_api.sh bg     # 后台启动
#   ./scripts/run_api.sh stop   # 停止服务
#   ./scripts/run_api.sh logs   # 查看日志

set -e

# 项目根目录
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

cd "$PROJECT_ROOT"

# 配置
HOST="${HOST:-0.0.0.0}"
PORT="${PORT:-8000}"
LOG_FILE="logs/api.log"

# 确保日志目录存在
mkdir -p logs

# 激活虚拟环境
if [ -f ".venv/bin/activate" ]; then
    source .venv/bin/activate
fi

# 设置 Python 路径
export PYTHONPATH="$PROJECT_ROOT:$PYTHONPATH"

case "${1:-start}" in
    start)
        echo "🚀 Starting FastAPI server at http://$HOST:$PORT"
        echo "📚 API docs: http://localhost:$PORT/docs"
        echo ""
        python -m web.server --host "$HOST" --port "$PORT"
        ;;
    
    dev)
        echo "🔧 Starting in development mode (auto-reload)..."
        echo "📚 API docs: http://localhost:$PORT/docs"
        echo ""
        python -m web.server --host "$HOST" --port "$PORT" --reload
        ;;
    
    bg)
        echo "🚀 Starting FastAPI server in background..."
        nohup python -m web.server --host "$HOST" --port "$PORT" > "$LOG_FILE" 2>&1 &
        PID=$!
        echo $PID > logs/api.pid
        echo "✅ Server started with PID: $PID"
        echo "📚 API docs: http://localhost:$PORT/docs"
        echo "📝 Logs: $LOG_FILE"
        ;;
    
    stop)
        if [ -f logs/api.pid ]; then
            PID=$(cat logs/api.pid)
            if kill -0 "$PID" 2>/dev/null; then
                kill "$PID"
                rm logs/api.pid
                echo "✅ Server stopped (PID: $PID)"
            else
                echo "⚠️ Server not running"
                rm logs/api.pid
            fi
        else
            echo "⚠️ PID file not found"
            # 尝试通过端口查找
            PID=$(lsof -ti :$PORT 2>/dev/null || true)
            if [ -n "$PID" ]; then
                echo "Found process on port $PORT: $PID"
                kill "$PID" && echo "✅ Killed"
            fi
        fi
        ;;
    
    logs)
        if [ -f "$LOG_FILE" ]; then
            tail -f "$LOG_FILE"
        else
            echo "⚠️ Log file not found: $LOG_FILE"
        fi
        ;;
    
    status)
        if [ -f logs/api.pid ]; then
            PID=$(cat logs/api.pid)
            if kill -0 "$PID" 2>/dev/null; then
                echo "✅ Server is running (PID: $PID)"
                echo "📚 URL: http://localhost:$PORT"
            else
                echo "❌ Server not running (stale PID file)"
            fi
        else
            # 检查端口
            PID=$(lsof -ti :$PORT 2>/dev/null || true)
            if [ -n "$PID" ]; then
                echo "✅ Found process on port $PORT: $PID"
            else
                echo "❌ Server not running"
            fi
        fi
        ;;
    
    *)
        echo "Usage: $0 {start|dev|bg|stop|logs|status}"
        exit 1
        ;;
esac
