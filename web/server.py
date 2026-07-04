"""FastAPI service entrypoint for quantitative trading APIs."""

import sys
import logging
from pathlib import Path

import uvicorn
from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

# 确保项目根目录在 Python 路径中
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stderr)]
)
logger = logging.getLogger("server")


def create_server() -> FastAPI:
    """创建完整的 FastAPI 服务"""
    from web.api import app as api_app
    
    # 静态文件目录
    static_dir = PROJECT_ROOT / "web" / "static"
    static_dir.mkdir(parents=True, exist_ok=True)
    
    # 挂载静态文件
    api_app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")
    
    # 首页路由
    @api_app.get("/", response_class=HTMLResponse)
    async def index():
        """API index page."""
        return HTMLResponse("""
        <!DOCTYPE html>
        <html>
        <head>
            <title>Quantitative Trading API</title>
            <meta charset="utf-8">
        </head>
        <body>
            <h1>Quantitative Trading API</h1>
            <ul>
                <li><a href="/docs">API 文档 (Swagger)</a></li>
                <li><a href="/api/stocks/list">股票列表</a></li>
            </ul>
        </body>
        </html>
        """)
    
    return api_app


# 创建服务实例
server = create_server()


def main():
    """运行服务"""
    import argparse
    
    parser = argparse.ArgumentParser(description="Quantitative Trading API Server")
    parser.add_argument("--host", default="0.0.0.0", help="Host to bind")
    parser.add_argument("--port", type=int, default=8000, help="Port to bind")
    parser.add_argument("--reload", action="store_true", help="Enable auto-reload")
    
    args = parser.parse_args()
    
    logger.info(f"Starting server at http://{args.host}:{args.port}")
    logger.info(f"API docs: http://localhost:{args.port}/docs")
    
    uvicorn.run(
        "web.server:server",
        host=args.host,
        port=args.port,
        reload=args.reload,
        log_level="info",
    )


if __name__ == "__main__":
    main()
