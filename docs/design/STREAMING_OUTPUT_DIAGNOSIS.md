# Streaming Output Diagnosis Guide

**Issue**: Second conversation appears to output all at once instead of streaming character by character.

**Date**: 2026-01-15

## Quick Diagnosis Steps

### 1. Check Logs

```bash
# Watch logs in real-time
scripts/run_web.sh logs

# Or tail the log file directly
tail -f logs/web.log
```

### 2. What to Look For

When you trigger the second conversation, look for these log entries:

#### ✅ Good Signs (Streaming Working)
```
INFO - Starting continue_chat with stream_mode='delta'
INFO - continue_chat chunk #1: keys=['_progress', '_status']
INFO -   Progress[0]: stage=llm, has_delta=True, has_answer=True
INFO -     delta length: 2
INFO - Got delta from framework: 2 chars
INFO - Returning delta: 2 chars
INFO - Sent delta #1: 2 chars, preview: '你好'
INFO - Sent delta #2: 3 chars, preview: '，我是'
INFO - Sent delta #3: 4 chars, preview: 'AI助手'
INFO - continue_chat completed: 150 total chunks, 45 delta events sent
```

#### ❌ Bad Signs (Streaming Not Working)
```
INFO - Starting continue_chat with stream_mode='delta'
INFO - continue_chat chunk #1: keys=['_progress', '_status']
INFO -   Progress[0]: stage=llm, has_delta=False, has_answer=True
INFO -     answer length: 200
WARNING - Delta field missing in continue_chat, using answer field (200 chars)
INFO - Returning delta: 200 chars
INFO - Sent delta #1: 200 chars, preview: '你好，我是AI助手，很高兴为你服务...'
INFO - continue_chat completed: 1 total chunks, 1 delta events sent
```

### 3. Interpret the Results

| Symptom | Diagnosis | Solution |
|---------|-----------|----------|
| `has_delta=True` but still outputs all at once | Frontend issue | Check browser console |
| `has_delta=False` + warning about missing delta | `stream_mode="delta"` not working | See Solution A below |
| Only 1-2 chunks total | LLM returning complete text in one chunk | See Solution B below |
| Many chunks but `delta_count=0` or =1 | Delta extraction failing | See Solution C below |

## Solutions

### Solution A: stream_mode="delta" Not Working

The Dolphin SDK may not support `stream_mode="delta"` for `continue_chat()`.

**Test**:
1. Check first conversation (arun) - does it stream properly?
2. If yes, the issue is specific to `continue_chat()`

**Fix**: Implement manual delta calculation for `continue_chat()`:

```python
# In agent_manager.py, around line 320
last_answer = ""  # Track cumulative answer

async for result in agent.continue_chat(message=message):  # Remove stream_mode
    # ... existing code ...
    
    if "_progress" in result:
        for prog in result["_progress"]:
            if prog.get("stage") == "llm":
                current_answer = prog.get("answer", "")
                if current_answer.startswith(last_answer):
                    delta = current_answer[len(last_answer):]
                    last_answer = current_answer
                else:
                    delta = current_answer  # Reset on discontinuous text
                    last_answer = current_answer
                
                if delta:
                    event_queue.put({"type": "delta", "content": delta})
```

### Solution B: LLM Returning Complete Text

Some LLMs/configurations buffer output and return it all at once.

**Check**:
- Model configuration in `config/dolphin.yaml`
- Model provider (OpenAI, Qwen, etc.)
- API streaming settings

**Fix**: Ensure streaming is enabled at the LLM level (not just Dolphin level).

### Solution C: Delta Extraction Failing

The `_process_streaming_result()` function may not be extracting delta correctly.

**Check**: Look for this specific log:
```
WARNING - Delta field missing in continue_chat, using answer field
```

**Fix**: The recent code update already handles this fallback. If you see this warning, it means `stream_mode="delta"` is not providing delta field.

## Testing

### Test First Conversation (arun)
1. Clear AI history
2. Click "解读页面数据" or send a message
3. Watch logs - should see multiple delta events

### Test Second Conversation (continue_chat)
1. Send another message (without clearing history)
2. Watch logs - should see similar delta pattern
3. Compare chunk_count and delta_count

### Expected Output
```
# First conversation
INFO - First run completed with 150 chunks

# Second conversation (should be similar)
INFO - continue_chat completed: 140 total chunks, 42 delta events sent
```

## Known Issues

1. **Event Loop**: Each request creates a new event loop, which may cause delays
2. **Streamlit Rerun**: Fragment rerun might buffer output
3. **Queue Timing**: Event queue may batch small deltas

## Next Steps

1. Run the web app with logging enabled
2. Trigger first and second conversations
3. Provide the log output
4. Based on logs, we can identify the exact issue

---

**Author**: AI Assistant  
**Last Updated**: 2026-01-15
