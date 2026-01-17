"""
Stocks API - 股票数据接口

提供页面数据的 JSON API。
"""

import logging
from typing import List, Optional
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

logger = logging.getLogger("stocks_api")

router = APIRouter(prefix="/api/stocks", tags=["stocks"])


# ==================== 数据模型 ====================

class StockInfo(BaseModel):
    """股票基本信息"""
    symbol: str
    name: str
    industry: Optional[str] = None
    market: Optional[str] = None


class StockQuote(BaseModel):
    """股票行情"""
    symbol: str
    name: str
    price: float
    change: float
    change_pct: float
    volume: Optional[float] = None
    amount: Optional[float] = None


# ==================== API 端点 ====================

@router.get("/list")
async def list_stocks(
    market: str = Query(default="A", description="市场：A, HK, US"),
    limit: int = Query(default=50, ge=1, le=500),
):
    """获取股票列表"""
    try:
        from web.data_service import DataService
        ds = DataService()
        
        # 根据市场获取符号
        if market == "A":
            symbols = ds.get_a_share_symbols(limit)
        elif market == "HK":
            symbols = ds.get_hk_symbols(limit) if hasattr(ds, 'get_hk_symbols') else []
        elif market == "US":
            symbols = ds.get_us_symbols(limit) if hasattr(ds, 'get_us_symbols') else []
        else:
            symbols = []
        
        return {"market": market, "count": len(symbols), "symbols": symbols}
    
    except Exception as e:
        logger.error(f"Failed to list stocks: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/quote/{symbol}")
async def get_quote(symbol: str):
    """获取单只股票行情"""
    try:
        from web.data_service import DataService
        ds = DataService()
        
        quote = ds.get_realtime_quote(symbol)
        if not quote:
            raise HTTPException(status_code=404, detail=f"Quote not found for {symbol}")
        
        return quote
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get quote for {symbol}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/ranking")
async def get_ranking(
    rank_type: str = Query(default="change_pct", description="排名类型"),
    direction: str = Query(default="desc", description="排序方向"),
    limit: int = Query(default=20, ge=1, le=100),
):
    """获取排行榜数据"""
    try:
        from web.data_service import DataService
        ds = DataService()
        
        data = ds.get_ranking_data(rank_type, direction, limit)
        return {"rank_type": rank_type, "direction": direction, "data": data}
    
    except Exception as e:
        logger.error(f"Failed to get ranking: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/moneyflow/{symbol}")
async def get_moneyflow(symbol: str):
    """获取资金流向数据"""
    try:
        from web.data_service import DataService
        ds = DataService()
        
        data = ds.get_moneyflow_data(symbol)
        if not data:
            raise HTTPException(status_code=404, detail=f"Moneyflow not found for {symbol}")
        
        return data
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get moneyflow for {symbol}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/technicals/{symbol}")
async def get_technicals(symbol: str):
    """获取技术指标数据"""
    try:
        from web.data_service import DataService
        ds = DataService()
        
        data = ds.get_technical_indicators(symbol)
        if not data:
            raise HTTPException(status_code=404, detail=f"Technicals not found for {symbol}")
        
        return data
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get technicals for {symbol}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/health")
async def health():
    """健康检查"""
    return {"status": "ok"}
