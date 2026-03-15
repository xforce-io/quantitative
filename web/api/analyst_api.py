"""
AI Analyst API - SSE 流式对话接口

真正的 Server-Sent Events 实现，替代 Streamlit Queue 模拟。
"""

import asyncio
import json
import logging
import sys
import uuid
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional, List, AsyncGenerator
from dataclasses import dataclass, field

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from web.dolphin_compat import apply_dolphin_web_compat
from web.dolphin_runtime import get_dolphin_runtime_async

# 配置日志
logger = logging.getLogger("analyst_api")
logger.setLevel(logging.INFO)
if not logger.handlers:
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(logging.Formatter('%(asctime)s - ANALYST_API - %(levelname)s - %(message)s'))
    logger.addHandler(handler)

# 项目路径
PROJECT_ROOT = Path(__file__).parent.parent.parent
AGENT_DPH_PATH = PROJECT_ROOT / "data" / "agents" / "stock_analyst" / "agent.dph"

router = APIRouter(prefix="/api/analyst", tags=["analyst"])


# ==================== 数据模型 ====================

class ChatRequest(BaseModel):
    """对话请求"""
    message: str = Field(..., min_length=1, description="用户消息")
    session_id: Optional[str] = Field(default=None, description="会话 ID")
    context: Optional[Dict[str, Any]] = Field(default=None, description="页面上下文")
    model_name: str = Field(default="qwen-plus", description="模型名称")


class ChatMessage(BaseModel):
    """对话消息"""
    role: str
    content: str
    timestamp: Optional[str] = None
    tool_calls: Optional[List[Dict[str, Any]]] = None


# ==================== 会话管理 ====================

@dataclass
class AgentSession:
    """Agent 会话状态"""
    session_id: str
    agent: Any = None
    messages: List[Dict[str, Any]] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.now)
    last_active: datetime = field(default_factory=datetime.now)
    is_first_run: bool = True
    context: Dict[str, Any] = field(default_factory=dict)


_sessions: Dict[str, AgentSession] = {}
def get_or_create_session(session_id: Optional[str]) -> AgentSession:
    """获取或创建会话"""
    if not session_id:
        session_id = str(uuid.uuid4())
    
    if session_id not in _sessions:
        _sessions[session_id] = AgentSession(session_id=session_id)
    
    session = _sessions[session_id]
    session.last_active = datetime.now()
    return session


def clear_session(session_id: str) -> bool:
    """清空会话"""
    if session_id in _sessions:
        del _sessions[session_id]
        return True
    return False


# ==================== SSE 流式生成器 ====================

async def _run_agent_stream(
    message: str,
    session: AgentSession,
    model_name: str = "qwen-plus",
) -> AsyncGenerator[Dict[str, Any], None]:
    """
    执行 Agent 并流式返回结果
    
    真正的 async generator，无需 Queue 桥接
    """
    from dolphin.sdk.agent.dolphin_agent import DolphinAgent

    apply_dolphin_web_compat()

    runtime = await get_dolphin_runtime_async()
    global_config = runtime["global_config"]
    global_skills = runtime["global_skills"]
    
    try:
        if session.is_first_run or session.agent is None:
            # ========== 首次请求：创建 Agent 并使用 arun ==========
            logger.info(f"First execution for session {session.session_id}")
            yield {"type": "progress", "stage": "init", "content": "正在初始化智能体..."}
            
            variables = {
                "model_name": model_name,
                "query": message,
            }
            
            # 添加页面上下文
            if session.context:
                variables["page_context"] = json.dumps(session.context, ensure_ascii=False)
            
            agent = DolphinAgent(
                name="stock_analyst_agent",
                file_path=str(AGENT_DPH_PATH),
                global_config=global_config,
                global_skills=global_skills,
                variables=variables,
            )
            
            await agent.initialize()
            
            # 设置 skills
            all_skills = global_skills.getAllSkills()
            if hasattr(agent, "executor") and hasattr(agent.executor, "context"):
                agent.executor.context.set_skills(all_skills)
                agent.executor.context.set_session_id(session.session_id)
            
            logger.info(f"Starting arun for session {session.session_id}")
            yield {"type": "progress", "stage": "run", "content": "正在分析..."}
            
            # 使用 stream_mode="delta"
            processed_tool_ids = set()
            chunk_count = 0
            full_response = ""
            tool_calls_list = []
            
            async for result in agent.arun(stream_mode="delta", **variables):
                chunk_count += 1
                
                if isinstance(result, dict) and "_progress" in result:
                    for prog in result.get("_progress", []):
                        if not isinstance(prog, dict):
                            continue
                        
                        stage = prog.get("stage", "")
                        status = prog.get("status", "")
                        
                        # LLM 阶段 - 直接使用 delta
                        if stage == "llm":
                            delta = prog.get("delta", "")
                            if delta:
                                full_response += delta
                                yield {"type": "delta", "content": delta}
                        
                        # 工具调用阶段
                        elif stage in ("skill", "tool_call"):
                            skill_info = prog.get("skill_info", {}) or {}
                            tool_name = skill_info.get("name", "") or prog.get("skill_name", "") or prog.get("tool_name", "")
                            tool_id = f"{tool_name}_{status}"
                            
                            if tool_name and tool_id not in processed_tool_ids:
                                processed_tool_ids.add(tool_id)
                                if status in ("processing", "running"):
                                    tool_info = {
                                        "name": tool_name,
                                        "args": skill_info.get("args", {}) or prog.get("args", {}),
                                    }
                                    tool_calls_list.append(tool_info)
                                    yield {"type": "tool_call", **tool_info}
                                elif status in ("completed", "success"):
                                    result_str = str(prog.get("answer", ""))[:500]
                                    yield {"type": "tool_result", "name": tool_name, "result": result_str}
            
            # 保存 Agent 和消息
            session.agent = agent
            session.is_first_run = False
            session.messages.append({
                "role": "user",
                "content": message,
                "timestamp": datetime.now().isoformat(),
            })
            session.messages.append({
                "role": "assistant",
                "content": full_response,
                "timestamp": datetime.now().isoformat(),
                "tool_calls": tool_calls_list if tool_calls_list else None,
            })
            
            logger.info(f"First run completed with {chunk_count} chunks")
            yield {"type": "done", "content": full_response}
        
        else:
            # ========== 后续请求：使用 continue_chat ==========
            logger.info(f"Continue session {session.session_id} with continue_chat")
            yield {"type": "progress", "stage": "continue", "content": "继续对话..."}
            
            agent = session.agent
            
            # 更新 query 变量
            try:
                if hasattr(agent, "executor") and hasattr(agent.executor, "context"):
                    agent.executor.context.variables["query"] = message
            except Exception as e:
                logger.debug(f"Could not update query variable: {e}")
            
            processed_tool_ids = set()
            chunk_count = 0
            full_response = ""
            tool_calls_list = []
            
            async for result in agent.continue_chat(message=message, stream_mode="delta"):
                chunk_count += 1
                
                if isinstance(result, dict) and "_progress" in result:
                    for prog in result.get("_progress", []):
                        if not isinstance(prog, dict):
                            continue
                        
                        stage = prog.get("stage", "")
                        status = prog.get("status", "")
                        
                        if stage == "llm":
                            delta = prog.get("delta", "")
                            if delta:
                                full_response += delta
                                yield {"type": "delta", "content": delta}
                        
                        elif stage in ("skill", "tool_call"):
                            skill_info = prog.get("skill_info", {}) or {}
                            tool_name = skill_info.get("name", "") or prog.get("skill_name", "") or prog.get("tool_name", "")
                            tool_id = f"{tool_name}_{status}"
                            
                            if tool_name and tool_id not in processed_tool_ids:
                                processed_tool_ids.add(tool_id)
                                if status in ("processing", "running"):
                                    tool_info = {
                                        "name": tool_name,
                                        "args": skill_info.get("args", {}) or prog.get("args", {}),
                                    }
                                    tool_calls_list.append(tool_info)
                                    yield {"type": "tool_call", **tool_info}
                                elif status in ("completed", "success"):
                                    result_str = str(prog.get("answer", ""))[:500]
                                    yield {"type": "tool_result", "name": tool_name, "result": result_str}
            
            if chunk_count == 0:
                logger.warning(f"continue_chat yielded 0 results")
                yield {"type": "error", "content": "AI 没有响应，请重试"}
            else:
                # 保存消息
                session.messages.append({
                    "role": "user",
                    "content": message,
                    "timestamp": datetime.now().isoformat(),
                })
                session.messages.append({
                    "role": "assistant",
                    "content": full_response,
                    "timestamp": datetime.now().isoformat(),
                    "tool_calls": tool_calls_list if tool_calls_list else None,
                })
                
                logger.info(f"continue_chat completed with {chunk_count} chunks")
                yield {"type": "done", "content": full_response}
    
    except Exception as e:
        logger.error(f"Agent execution failed: {e}", exc_info=True)
        yield {"type": "error", "content": str(e)}


# ==================== API 端点 ====================

@router.post("/chat")
async def chat(request: ChatRequest):
    """
    AI 分析师对话接口（SSE 流式响应）
    """
    session = get_or_create_session(request.session_id)
    
    # 更新上下文
    if request.context:
        session.context.update(request.context)
    
    async def event_generator():
        try:
            async for event in _run_agent_stream(
                message=request.message,
                session=session,
                model_name=request.model_name,
            ):
                yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
            
            # 最终事件，返回 session_id
            yield f"data: {json.dumps({'type': 'end', 'session_id': session.session_id}, ensure_ascii=False)}\n\n"
        
        except Exception as e:
            logger.error(f"SSE stream error: {e}", exc_info=True)
            yield f"data: {json.dumps({'type': 'error', 'content': str(e)}, ensure_ascii=False)}\n\n"
    
    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # 禁用 nginx 缓冲
        }
    )


@router.get("/history/{session_id}")
async def get_history(session_id: str):
    """获取对话历史"""
    session = _sessions.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    
    return {
        "session_id": session_id,
        "messages": session.messages,
        "created_at": session.created_at.isoformat(),
        "last_active": session.last_active.isoformat(),
    }


@router.post("/clear/{session_id}")
async def clear(session_id: str):
    """清空对话历史"""
    if clear_session(session_id):
        return {"status": "ok", "message": f"Session {session_id} cleared"}
    else:
        raise HTTPException(status_code=404, detail="Session not found")


@router.get("/sessions")
async def list_sessions():
    """列出所有会话"""
    return {
        "count": len(_sessions),
        "sessions": [
            {
                "session_id": s.session_id,
                "message_count": len(s.messages),
                "created_at": s.created_at.isoformat(),
                "last_active": s.last_active.isoformat(),
            }
            for s in _sessions.values()
        ]
    }


@router.get("/health")
async def health():
    """健康检查"""
    return {"status": "ok", "timestamp": datetime.now().isoformat()}
