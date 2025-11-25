# Fix: Streaming Fallback Due to AttributeError

**Date**: 2025-11-18
**Priority**: P1 (High - UX Impact)
**Status**: ✅ Fixed

---

## Problem Description

### Symptom
When users sent messages in the chat, they experienced:
- Message showed "Generando respuesta..." for a few seconds
- Then the **entire response appeared at once** (no streaming)
- No incremental word-by-word display

### Expected Behavior
- Streaming enabled by default (`stream: true`)
- Words should appear **incrementally** as they're generated
- Real-time typing effect for better UX

### Actual Behavior
- Streaming was **silently failing** and falling back to non-streaming mode
- Frontend console showed: `"Streaming failed, falling back to non-streaming Error: AttributeError"`

---

## Root Cause Analysis

### Error Details

**Frontend Error** (Browser Console):
```
Streaming failed, falling back to non-streaming Error: AttributeError
    at eval (ChatView.tsx:640:27)
```

**Backend Error** (API Logs):
```json
{
  "error": "'dict' object has no attribute 'delta'",
  "exc_type": "AttributeError",
  "traceback": "File \"/app/src/routers/chat/handlers/streaming_handler.py\", line 333, in producer\n    delta = chunk.choices[0].delta\n            ^^^^^^^^^^^^^^^^^^^^^^\nAttributeError: 'dict' object has no attribute 'delta'"
}
```

### Root Cause

**File**: `apps/api/src/routers/chat/handlers/streaming_handler.py`
**Line**: 333

The streaming handler assumed that `chunk.choices[0]` would always be an **object** with a `.delta` attribute:

```python
# BROKEN CODE (line 333)
delta = chunk.choices[0].delta  # ❌ Fails if choices[0] is a dict
```

However, the Saptiva API client was returning `choices[0]` as a **dict**, not an object. This caused:

1. **AttributeError** when trying to access `.delta` on a dict
2. Exception caught by `try-catch` in streaming handler
3. Error event sent to frontend via SSE
4. Frontend catch block triggered fallback to non-streaming mode
5. User sees complete message at once instead of streaming

---

## Solution

### Code Changes

**File**: `apps/api/src/routers/chat/handlers/streaming_handler.py`
**Lines**: 330-341

**Before** (Broken):
```python
# Extract content from chunk
content = ""
if hasattr(chunk, 'choices') and chunk.choices:
    delta = chunk.choices[0].delta  # ❌ AttributeError if dict
    if hasattr(delta, 'content') and delta.content:
        content = delta.content
```

**After** (Fixed):
```python
# Extract content from chunk
content = ""
if hasattr(chunk, 'choices') and chunk.choices:
    choice = chunk.choices[0]
    # Handle both object and dict responses from Saptiva
    if isinstance(choice, dict):
        delta = choice.get('delta', {})
        content = delta.get('content', '') if isinstance(delta, dict) else (delta.content if hasattr(delta, 'content') else '')
    else:
        delta = choice.delta if hasattr(choice, 'delta') else None
        if delta and hasattr(delta, 'content') and delta.content:
            content = delta.content
```

### What Changed

✅ **Added type checking** with `isinstance(choice, dict)`
✅ **Dict access** using `.get()` when `choice` is a dict
✅ **Object access** using `.delta` when `choice` is an object
✅ **Graceful fallback** if neither format matches (returns empty string)

This handles both API response formats:
1. **Dict format**: `{"delta": {"content": "text"}}`
2. **Object format**: `SomeObject.delta.content`

---

## Testing

### Manual Testing

1. **Start the application**:
   ```bash
   make dev
   ```

2. **Send a chat message** in the UI (http://localhost:3000)

3. **Expected result**:
   - Text appears **word by word** in real-time ✅
   - No "Generando respuesta..." delay ✅
   - Smooth typing animation ✅

4. **Check browser console**:
   - Should NOT show `"Streaming failed"` error ✅

5. **Check API logs**:
   ```bash
   docker logs octavios-chat-client-project-api --tail 50 | grep -i "streaming\|error"
   ```
   - Should NOT show `AttributeError: 'dict' object has no attribute 'delta'` ✅

### Verification Logs

After fix, you should see streaming logs like:
```json
{"event": "Starting Saptiva stream (producer)", "model": "Saptiva Turbo"}
{"event": "Producer completed successfully", "response_length": 234}
```

---

## Impact

### Before Fix ❌
- Streaming **always failed** silently
- Users saw complete responses (bad UX)
- Frontend console showed AttributeError
- Fallback to slower non-streaming mode every time

### After Fix ✅
- Streaming **works correctly**
- Real-time word-by-word display (excellent UX)
- No console errors
- Faster perceived response time

---

## Related Files

### Modified
- `apps/api/src/routers/chat/handlers/streaming_handler.py` (lines 330-341)

### Reviewed
- `apps/web/src/app/chat/_components/ChatView.tsx` (streaming fallback logic) ✅
- `apps/api/src/services/saptiva_client.py` (API response format) ✅

---

## Lessons Learned

### API Response Handling
When working with external APIs (like Saptiva):
1. ✅ **Never assume response structure** - always validate types
2. ✅ **Handle both dict and object formats** for resilience
3. ✅ **Use `.get()` for dicts** instead of direct attribute access
4. ✅ **Log response structure** during development to catch format changes

### Streaming Best Practices
1. ✅ **Test streaming explicitly** - it's easy to miss in development
2. ✅ **Check browser console** for silent errors
3. ✅ **Monitor backend logs** for exception patterns
4. ✅ **Implement graceful degradation** (fallback to non-streaming)

---

## Deployment Notes

### Breaking Changes
❌ None - This is a pure bugfix

### Rollback Plan
If issues arise, revert commit and streaming will fallback to non-streaming (current behavior).

### Monitoring
After deployment, verify:
1. **Streaming success rate**: No more AttributeError in logs
2. **User experience**: Real-time text display
3. **Error logs**: Search for `"Streaming failed"` - should be 0

---

## References

- **Streaming Handler**: `apps/api/src/routers/chat/handlers/streaming_handler.py`
- **Frontend Streaming**: `apps/web/src/app/chat/_components/ChatView.tsx` (lines 593-665)
- **Saptiva Client**: `apps/api/src/services/saptiva_client.py`

---

## Related Issues

- **History Bug Fix**: `docs/bugfixes/HISTORY_SAVE_BUG_FIX.md` (fixed same session)
- Both issues were P0/P1 bugs affecting core chat functionality
