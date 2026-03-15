"""
Agent Manager - Simplified Reliable Version

Reverted to proven approach with manual delta calculation.
This version is tested and should work reliably.
"""

import asyncio
import json
import os
import logging
import sys
import threading
import queue
from pathlib import Path
from typing import Dict, Any, Optional, List, Generator, Tuple
from dataclasses import dataclass, field
from datetime import datetime

from web.dolphin_compat import apply_dolphin_web_compat
from web.dolphin_runtime import get_dolphin_runtime

# Configure logging
_logger = logging.getLogger("agent_manager")
_logger.setLevel(logging.INFO)
if not _logger.handlers:
    _handler = logging.StreamHandler(sys.stderr)
    _handler.setLevel(logging.INFO)
    _handler.setFormatter(logging.Formatter('%(asctime)s - AGENT - %(levelname)s - %(message)s'))
    _logger.addHandler(_handler)

# Project root
PROJECT_ROOT = Path(__file__).parent.parent
AGENT_DPH_PATH = PROJECT_ROOT / "data" / "agents" / "stock_analyst" / "agent.dph"


# ==================== Exception Classes ====================

class AgentConfigurationError(Exception):
    """Agent configuration error"""
    pass


class AgentExecutionError(Exception):
    """Agent execution error"""
    pass


def _init_dolphin_runtime():
    """Initialize Dolphin Agent Runtime (lazy loading)."""
    try:
        return get_dolphin_runtime()
    except RuntimeError as e:
        if "not available" in str(e):
            raise AgentConfigurationError(str(e)) from e
        raise AgentExecutionError(f"Dolphin runtime initialization failed: {e}") from e


# ==================== Session Management ====================

@dataclass
class AgentSession:
    """Agent session state"""
    session_id: str
    agent: Any = None
    created_at: datetime = field(default_factory=datetime.now)
    last_active: datetime = field(default_factory=datetime.now)
    is_first_run: bool = True


_sessions: Dict[str, AgentSession] = {}
_sessions_lock = threading.Lock()


def get_or_create_session(session_id: str) -> AgentSession:
    """Get or create session"""
    with _sessions_lock:
        if session_id not in _sessions:
            _sessions[session_id] = AgentSession(session_id=session_id)
        session = _sessions[session_id]
        session.last_active = datetime.now()
        return session


def clear_session(session_id: str):
    """Clear session"""
    with _sessions_lock:
        if session_id in _sessions:
            del _sessions[session_id]


# ==================== Streaming Execution ====================

def _run_agent_in_thread(
    message: str,
    session_id: str,
    model_name: Optional[str],
    event_queue: queue.Queue,
):
    """
    Run Agent in background thread, send events via queue
    
    Uses proven manual delta calculation approach.
    """
    async def _run():
        from dolphin.sdk.agent.dolphin_agent import DolphinAgent

        apply_dolphin_web_compat()
        
        runtime = _init_dolphin_runtime()
        session = get_or_create_session(session_id)
        
        global_config = runtime["global_config"]
        global_skills = runtime["global_skills"]
        
        _model_name = model_name or "qwen-plus"
        
        try:
            if session.is_first_run or session.agent is None:
                # ========== First request: create agent and use arun ==========
                _logger.info(f"First execution for session {session_id}")
                event_queue.put({"type": "progress", "stage": "init", "content": "正在初始化智能体..."})
                
                variables = {
                    "model_name": _model_name,
                    "query": message,
                }
                
                agent = DolphinAgent(
                    name="stock_analyst_agent",
                    file_path=str(AGENT_DPH_PATH),
                    global_config=global_config,
                    global_skills=global_skills,
                    variables=variables,
                )
                
                await agent.initialize()
                
                # Set skills
                all_skills = global_skills.getAllSkills()
                if hasattr(agent, "executor") and hasattr(agent.executor, "context"):
                    agent.executor.context.set_skills(all_skills)
                    agent.executor.context.set_session_id(session_id)
                
                _logger.info(f"Starting arun for session {session_id} (stream_mode=delta)")
                event_queue.put({"type": "progress", "stage": "run", "content": "正在执行..."})
                
                # Use stream_mode="delta" - SDK auto-calculates delta for us!
                processed_tool_ids = set()
                chunk_count = 0
                async for result in agent.arun(stream_mode="delta", **variables):
                    chunk_count += 1
                    
                    if chunk_count % 100 == 0:
                        _logger.info(f"arun chunk #{chunk_count}")
                    
                    # Process _progress - directly use delta field
                    if isinstance(result, dict) and "_progress" in result:
                        for prog in result.get("_progress", []):
                            if not isinstance(prog, dict):
                                continue
                            
                            stage = prog.get("stage", "")
                            status = prog.get("status", "")
                            
                            # LLM stage - use delta field directly (SDK calculates it)
                            if stage == "llm":
                                delta = prog.get("delta", "")
                                if delta:
                                    event_queue.put({"type": "delta", "content": delta})
                            
                            # Skill/Tool stage
                            elif stage in ("skill", "tool_call"):
                                skill_info = prog.get("skill_info", {}) or {}
                                tool_name = skill_info.get("name", "") or prog.get("skill_name", "") or prog.get("tool_name", "")
                                tool_id = f"{tool_name}_{status}"
                                
                                if tool_name and tool_id not in processed_tool_ids:
                                    processed_tool_ids.add(tool_id)
                                    if status in ("processing", "running"):
                                        event_queue.put({
                                            "type": "tool_call",
                                            "name": tool_name,
                                            "args": skill_info.get("args", {}) or prog.get("args", {}) or prog.get("skill_args", {}),
                                        })
                                    elif status in ("completed", "success"):
                                        event_queue.put({
                                            "type": "tool_result",
                                            "name": tool_name,
                                            "result": str(prog.get("answer", ""))[:500],
                                        })
                
                # Save agent
                session.agent = agent
                session.is_first_run = False
                
                _logger.info(f"First run completed with {chunk_count} chunks")
            
            else:
                # ========== Subsequent requests: use continue_chat with stream_mode="delta" ==========
                _logger.info(f"Continue session {session_id} with continue_chat (stream_mode=delta)")
                event_queue.put({"type": "progress", "stage": "continue", "content": "继续对话..."})
                
                agent = session.agent
                
                # Update query variable
                try:
                    if hasattr(agent, "executor") and hasattr(agent.executor, "context"):
                        agent.executor.context.variables["query"] = message
                except Exception as e:
                    _logger.debug(f"Could not update query variable: {e}")
                
                # Track processed tool calls to avoid duplicates
                processed_tool_ids = set()
                
                chunk_count = 0
                # Use stream_mode="delta" - SDK auto-calculates delta for us!
                async for result in agent.continue_chat(message=message, stream_mode="delta"):
                    chunk_count += 1
                    
                    if chunk_count % 100 == 0:
                        _logger.info(f"continue_chat chunk #{chunk_count}")
                    
                    # Process _progress - directly use delta field
                    if isinstance(result, dict) and "_progress" in result:
                        for prog in result.get("_progress", []):
                            if not isinstance(prog, dict):
                                continue
                            
                            stage = prog.get("stage", "")
                            status = prog.get("status", "")
                            
                            # LLM stage - use delta field directly (SDK calculates it)
                            if stage == "llm":
                                delta = prog.get("delta", "")
                                if delta:
                                    event_queue.put({"type": "delta", "content": delta})
                            
                            # Skill/Tool stage
                            elif stage in ("skill", "tool_call"):
                                skill_info = prog.get("skill_info", {}) or {}
                                tool_name = skill_info.get("name", "") or prog.get("skill_name", "") or prog.get("tool_name", "")
                                # Use unique ID based on tool name + status to avoid duplicates
                                tool_id = f"{tool_name}_{status}"
                                
                                if tool_name and tool_id not in processed_tool_ids:
                                    processed_tool_ids.add(tool_id)
                                    if status in ("processing", "running"):
                                        event_queue.put({
                                            "type": "tool_call",
                                            "name": tool_name,
                                            "args": skill_info.get("args", {}) or prog.get("args", {}) or prog.get("skill_args", {}),
                                        })
                                    elif status in ("completed", "success"):
                                        event_queue.put({
                                            "type": "tool_result",
                                            "name": tool_name,
                                            "result": str(prog.get("answer", ""))[:500],
                                        })
                
                if chunk_count == 0:
                    _logger.warning(f"continue_chat yielded 0 results for session {session_id}")
                    event_queue.put({"type": "error", "message": "AI 没有响应，请重试或刷新页面"})
                else:
                    _logger.info(f"continue_chat completed with {chunk_count} chunks")
            
            event_queue.put({"type": "done", "content": ""})
        
        except Exception as e:
            _logger.error(f"Agent execution failed: {e}", exc_info=True)
            event_queue.put({"type": "error", "message": str(e)})
        
        finally:
            event_queue.put(None)
    
    # Run in new event loop
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    try:
        loop.run_until_complete(_run())
    except Exception as e:
        _logger.error(f"Loop execution error: {e}", exc_info=True)
    finally:
        loop.close()


def run_agent_stream_sync(
    message: str,
    session_id: str,
    model_name: Optional[str] = None,
) -> Generator[Dict[str, Any], None, None]:
    """
    Synchronous version of Agent execution (true streaming output)
    
    Uses background thread to run Agent, bridges async and sync via queue.
    """
    event_queue = queue.Queue()
    
    # Start background thread
    thread = threading.Thread(
        target=_run_agent_in_thread,
        args=(message, session_id, model_name, event_queue),
        daemon=True,
    )
    
    # Inject Streamlit context
    try:
        from streamlit.runtime.scriptrunner import add_script_run_ctx
        add_script_run_ctx(thread)
    except ImportError:
        _logger.warning("Could not import add_script_run_ctx")
        
    thread.start()
    
    # Read events from queue and yield
    while True:
        try:
            event = event_queue.get(timeout=120)
            if event is None:
                break
            yield event
        except queue.Empty:
            yield {"type": "error", "message": "Agent 执行超时"}
            break


# ==================== Compatibility Layer ====================

class AgentManager:
    """Agent Manager (compatibility layer)"""
    
    def __init__(self):
        pass
    
    def get_or_create_session(self, session_id: str) -> AgentSession:
        return get_or_create_session(session_id)
    
    def clear_session(self, session_id: str):
        clear_session(session_id)
    
    def chat_stream(self, session_id: str, user_message: str) -> Generator[Dict[str, Any], None, None]:
        for event in run_agent_stream_sync(user_message, session_id):
            yield event
    
    def chat(self, session_id: str, user_message: str) -> str:
        full_response = ""
        for event in self.chat_stream(session_id, user_message):
            if event["type"] == "delta":
                full_response += event["content"]
            elif event["type"] == "error":
                return f"错误: {event['message']}"
        return full_response


_agent_manager = None


def get_agent_manager() -> AgentManager:
    global _agent_manager
    if _agent_manager is None:
        _agent_manager = AgentManager()
    return _agent_manager
