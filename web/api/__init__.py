"""
AI Analyst FastAPI Application

现代化 Web API，替代 Streamlit 实现真正的流式输出。
"""

import os
from pathlib import Path
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

# 项目根目录
PROJECT_ROOT = Path(__file__).parent.parent.parent


def create_app() -> FastAPI:
    """创建 FastAPI 应用"""
    app = FastAPI(
        title="Quantitative Trading AI Analyst",
        description="AI 驱动的量化投研分析平台",
        version="2.0.0",
    )

    # CORS 中间件
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # 注册路由
    from web.api.analyst_api import router as analyst_router
    from web.api.stocks_api import router as stocks_router
    
    app.include_router(analyst_router)
    app.include_router(stocks_router)

    # 挂载静态文件
    static_dir = PROJECT_ROOT / "web" / "static"
    if static_dir.exists():
        app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

    # 页面路由
    from fastapi.responses import FileResponse, HTMLResponse
    
    @app.get("/", response_class=HTMLResponse)
    async def index():
        """首页 - AI 分析师页面"""
        analyst_html = static_dir / "analyst.html"
        if analyst_html.exists():
            return FileResponse(analyst_html)
        else:
            return HTMLResponse("""
            <!DOCTYPE html>
            <html>
            <head><title>Quantitative Trading AI</title></head>
            <body>
                <h1>🚀 FastAPI Server Running</h1>
                <p>请创建 web/static/analyst.html 文件</p>
                <ul>
                    <li><a href="/docs">API 文档</a></li>
                    <li><a href="/api/analyst/health">健康检查</a></li>
                </ul>
            </body>
            </html>
            """)
    
    @app.get("/analyst", response_class=HTMLResponse)
    async def analyst_page():
        """AI 分析师页面"""
        analyst_html = static_dir / "analyst.html"
        if analyst_html.exists():
            return FileResponse(analyst_html)
        else:
            return HTMLResponse("<h1>analyst.html not found</h1>", status_code=404)

    return app


# 创建应用实例
app = create_app()
