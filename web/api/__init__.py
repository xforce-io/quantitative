"""FastAPI application for quantitative trading web APIs."""

from pathlib import Path
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

# 项目根目录
PROJECT_ROOT = Path(__file__).parent.parent.parent


def create_app() -> FastAPI:
    """创建 FastAPI 应用"""
    app = FastAPI(
        title="Quantitative Trading API",
        description="量化交易数据接口",
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
    from web.api.stocks_api import router as stocks_router

    app.include_router(stocks_router)

    # 挂载静态文件
    static_dir = PROJECT_ROOT / "web" / "static"
    if static_dir.exists():
        app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

    # 页面路由
    from fastapi.responses import HTMLResponse
    
    @app.get("/", response_class=HTMLResponse)
    async def index():
        """API index."""
        return HTMLResponse("""
        <!DOCTYPE html>
        <html>
        <head><title>Quantitative Trading API</title></head>
        <body>
            <h1>Quantitative Trading API</h1>
            <ul>
                <li><a href="/docs">API 文档</a></li>
                <li><a href="/api/stocks/list">股票列表</a></li>
            </ul>
        </body>
        </html>
        """)

    return app


# 创建应用实例
app = create_app()
