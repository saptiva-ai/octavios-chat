# 📊 OCR Benchmark Report (AlphaXiv)

**Generated**: 2025-11-03 18:36:50
**PDF**: /tmp/test_data/Capital414_presentacion.pdf
**Pages Tested**: [1, 3, 4]

## Performance Summary

| Strategy | Success Rate | Avg Duration | Total Chars | Total Words | Status |
|----------|--------------|--------------|-------------|-------------|--------|
| Saptiva OCR | 3/3 (100.0%) | 100.2ms | 1,056 | 146 | ✅ Success |
| DeepSeek OCR (AlphaXiv) | 3/3 (100.0%) | 11500.1ms | 278 | 40 | ✅ Success |

## Text Similarity (Accuracy)

| Comparison | Similarity |
|------------|------------|
| Saptiva OCR vs DeepSeek OCR (AlphaXiv) | 8.52% |

## 🏆 Best Performers

**Fastest**: Saptiva OCR (300.58ms total)
**Most Text Extracted**: Saptiva OCR (1,056 chars)

## 💡 Recommendation

❌ **LOW SIMILARITY** - Strategies produce significantly different results

## Detailed Results per Page

### Saptiva OCR

| Page | Chars | Words | Duration | Status |
|------|-------|-------|----------|--------|
| 1 | 237 | 19 | 135.56ms | ✅ |
| 3 | 30 | 6 | 75.82ms | ✅ |
| 4 | 789 | 121 | 88.60ms | ✅ |

### DeepSeek OCR (AlphaXiv)

| Page | Chars | Words | Duration | Status |
|------|-------|-------|----------|--------|
| 1 | 89 | 13 | 4222.66ms | ✅ |
| 3 | 189 | 27 | 2338.32ms | ✅ |
| 4 | 0 | 0 | 27938.60ms | ✅ |
