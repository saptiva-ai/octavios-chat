# FIXES FOR CAPITAL 414 PRODUCTION ISSUES

## Summary of Issues

1. **Silent failures with file attachments** - streaming handler lacks error propagation
2. **Qwen identity leakage** - mentions Alibaba/China due to empty prompt config
3. **Turbo truncation** - max_tokens too low (800)
4. **Hallucinations about 414 Capital** - no explicit guardrails for unknown entities
5. **No follow-up after failed turn** - frontend doesn't recover from backend errors

## Root Causes

### Backend (FastAPI)
- `streaming_handler.py`: No try-catch around document processing and LLM streaming
- `streaming_handler.py`: Hardcoded "Eres un asistente útil" instead of using prompt registry
- `registry.yaml`: Empty config for "Saptiva Cortex" allows model default identity
- `registry.yaml`: Insufficient max_tokens for Turbo (800 → should be ~1500)

### Frontend (Next.js)
- `ChatView.tsx`: Error handling exists but UX needs better visibility
- No explicit error message display when streaming fails silently

---

## Fixes Applied

See the following patches for detailed changes:

1. **FIX-001**: Streaming handler error propagation (`streaming_handler.py`)
2. **FIX-002**: Centralized Saptiva identity for all models (`registry.yaml`)
3. **FIX-003**: Increase Turbo max_tokens and add hallucination guardrails (`registry.yaml`)
4. **FIX-004**: Frontend error display improvements (`ChatView.tsx`)

---

## Testing Checklist

After applying fixes, test the following scenarios:

### File Attachments
- [ ] Upload PDF, send message → assistant responds (not silent)
- [ ] Upload invalid file → clear error message displayed
- [ ] Upload PDF with extraction failure → graceful degradation

### Model Identity
- [ ] Ask Qwen "¿quién eres?" → mentions Saptiva, NOT Alibaba
- [ ] Ask Turbo "¿dónde están tus servidores?" → mentions Saptiva infra, NOT external
- [ ] Ask Ops "¿qué modelo eres?" → Saptiva identity, NOT raw model name

### Hallucinations
- [ ] Ask "¿quién es 414 Capital?" → says "no tengo información específica" OR uses documents
- [ ] Ask about unknown company → does NOT fabricate details

### Error Recovery
- [ ] Send message with file, get error → can send follow-up message successfully
- [ ] Network failure mid-stream → frontend shows error, can retry

### Truncation
- [ ] Turbo: ask for 3-paragraph summary → completes full response (not cut mid-sentence)

---

## Deployment Notes

1. **No rebuild needed** - hot reload will pick up Python changes
2. **Restart API service** to reload `registry.yaml`:
   ```bash
   make reload-env-service SERVICE=api
   ```
3. **Clear Redis cache** (optional but recommended):
   ```bash
   docker compose exec redis redis-cli FLUSHDB
   ```
4. **Monitor logs** during first production test:
   ```bash
   docker compose logs -f api | grep -E "ERROR|streaming"
   ```

