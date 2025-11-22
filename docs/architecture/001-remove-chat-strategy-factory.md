# ADR 001: Remove ChatStrategyFactory

**Date**: 2025-11-10  
**Status**: Proposed  
**Deciders**: Development Team  
**Context**: Phase 2 - Removing Unnecessary Abstractions

---

## Context and Problem Statement

The `ChatStrategyFactory` exists in `apps/api/src/domain/chat_strategy.py` but **always returns the same type** (`SimpleChatStrategy`).

**Current implementation**:
```python
class ChatStrategyFactory:
    @staticmethod
    def create_strategy(context: ChatContext, chat_service: ChatService) -> ChatStrategy:
        logger.debug("Creating SimpleChatStrategy")
        return SimpleChatStrategy(chat_service)  # Always same type!
```

**Usage**: 2 call sites
- `apps/api/src/routers/chat.py:1373`
- `apps/api/src/routers/chat_new_endpoint.py:67`

**Questions**:
1. Does this factory add value today?
2. Is there a documented roadmap for additional strategies?
3. Does removing it violate Open/Closed Principle?

---

## Decision Drivers

### **YAGNI Principle**
*"You Aren't Gonna Need It"*

- No roadmap found for additional strategies
- No TODO/FIXME comments about future strategies
- Git history shows no intention of multiple implementations

### **Current Reality**
```python
# What we have:
strategy = ChatStrategyFactory.create_strategy(context, chat_service)

# What we actually mean:
strategy = SimpleChatStrategy(chat_service)
```

### **Complexity Cost**
- Additional layer of indirection
- Harder to trace in debugging
- Misleading abstraction (implies choice when there is none)

---

## Considered Options

### **Option 1: Remove Factory** ✅ **RECOMMENDED**

**Direct instantiation**:
```python
# In chat.py and chat_new_endpoint.py
strategy = SimpleChatStrategy(chat_service)
result = await strategy.process(context)
```

**Pros**:
- ✅ Honest code (no false abstraction)
- ✅ Easier to understand
- ✅ Less indirection
- ✅ YAGNI compliance

**Cons**:
- ❌ Must change 2 call sites
- ❌ Harder to add strategies later (but we can when needed!)

---

### **Option 2: Keep Factory, Document Roadmap**

**Add multiple strategies NOW**:
```python
class ChatStrategyFactory:
    @staticmethod
    def create_strategy(context: ChatContext, chat_service: ChatService) -> ChatStrategy:
        if context.tools_enabled.get("research"):
            return ResearchChatStrategy(chat_service)
        elif context.tools_enabled.get("web_search"):
            return WebSearchChatStrategy(chat_service)
        else:
            return SimpleChatStrategy(chat_service)
```

**Pros**:
- ✅ Factory justified by real selection logic
- ✅ Open/Closed principle preserved

**Cons**:
- ❌ Requires implementing strategies that may not be needed
- ❌ Violates YAGNI (building for hypothetical future)

---

### **Option 3: Keep As-Is, Document Intent**

Add comment explaining future roadmap.

**Pros**:
- ✅ No code changes

**Cons**:
- ❌ Still complexity without benefit
- ❌ Technical debt remains

---

## Decision Outcome

**Chosen Option**: **Option 1 - Remove Factory**

### **Rationale**:

1. **Honesty Over Cleverness**
   - Code should reflect reality
   - One strategy = no factory needed

2. **YAGNI Compliance**
   - No documented need for multiple strategies
   - When we need it, we'll add it (with TDD!)

3. **Reversibility**
   - If future strategies emerge, re-adding factory is straightforward
   - Strategy pattern interface (`ChatStrategy`) remains intact

4. **Simplicity**
   - Reduces cognitive load
   - Easier onboarding for new developers

### **Migration Plan**:

1. Replace factory calls with direct instantiation:
   ```python
   # Before:
   strategy = ChatStrategyFactory.create_strategy(context, chat_service)
   
   # After:
   strategy = SimpleChatStrategy(chat_service)
   ```

2. Keep `ChatStrategy` abstract base class (for future extensibility)

3. Document in `CONTRIBUTING.md`:
   - When to add abstractions (2+ implementations)
   - How to re-introduce factory when needed

---

## Consequences

### **Positive**:
- ✅ Simpler codebase
- ✅ Honest abstractions
- ✅ YAGNI compliance
- ✅ Zero functional change

### **Negative**:
- ⚠️ If strategies are added later, must re-introduce factory
- ⚠️ Change required in 2 files

### **Neutral**:
- `ChatStrategy` interface remains (good for future)
- Tests unchanged (strategy pattern still works)

---

## Validation

### **Before Removal**:
```bash
# Verify only 2 call sites
grep -r "ChatStrategyFactory.create" apps/api/src/
```

### **After Removal**:
```bash
# Run tests to ensure no breakage
make test-api

# Verify no references remain
grep -r "ChatStrategyFactory" apps/api/src/
```

---

## Notes

### **When to Re-introduce Factory**:

Add factory back when **2+ concrete strategies** exist:

```python
# Justified factory (multiple implementations):
class ChatStrategyFactory:
    @staticmethod
    def create(context: ChatContext) -> ChatStrategy:
        if context.has_documents():
            return RAGChatStrategy(...)
        elif context.tools_enabled["research"]:
            return ResearchChatStrategy(...)
        else:
            return SimpleChatStrategy(...)
```

### **Alternative Pattern**:

Instead of factory, consider **strategy injection**:
```python
# Let caller decide strategy
async def process_chat(context: ChatContext, strategy: ChatStrategy):
    return await strategy.process(context)
```

---

## References

- [YAGNI Principle](https://martinfowler.com/bliki/Yagni.html)
- [Tell, Don't Ask](https://martinfowler.com/bliki/TellDontAsk.html)
- ADR Template: [Michael Nygard's ADRs](https://github.com/joelparkerhenderson/architecture-decision-record)

---

**Next ADR**: 002 - Test Fixture Consolidation Strategy

