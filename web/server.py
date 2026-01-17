"""
FastAPI 主服务入口

替代 Streamlit 的现代化 Web 服务。
"""

import os
import sys
import logging
from pathlib import Path

import uvicorn
from fastapi import FastAPI
from fastapi.responses import FileResponse, HTMLResponse
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
        """首页 - 重定向到 AI 分析师页面"""
        analyst_html = static_dir / "analyst.html"
        if analyst_html.exists():
            return FileResponse(analyst_html)
        else:
            return HTMLResponse("""
            <!DOCTYPE html>
            <html>
            <head>
                <title>Quantitative Trading AI</title>
                <meta charset="utf-8">
            </head>
            <body>
                <h1>🚀 FastAPI Server Running</h1>
                <p>静态页面尚未创建，请访问 API 文档：</p>
                <ul>
                    <li><a href="/docs">API 文档 (Swagger)</a></li>
                    <li><a href="/api/analyst/health">AI 分析师健康检查</a></li>
                    <li><a href="/api/stocks/health">股票 API 健康检查</a></li>
                </ul>
            </body>
            </html>
            """)
    
    @api_app.get("/analyst", response_class=HTMLResponse)
    async def analyst_page():
        """AI 分析师页面"""
        analyst_html = static_dir / "analyst.html"
        if analyst_html.exists():
            return FileResponse(analyst_html)
        else:
            return HTMLResponse("<h1>analyst.html not found</h1>", status_code=404)
    
    return api_app


# 创建服务实例
server = create_server()


def main():
    """运行服务"""
    import argparse
    
    parser = argparse.ArgumentParser(description="Quantitative Trading AI Server")
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
