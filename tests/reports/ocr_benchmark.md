# 📊 OCR Benchmark Report

**Generated**: 2025-11-03 17:59:56
**PDF**: /tmp/test_data/Capital414_presentacion.pdf
**Pages Tested**: [1, 2]

## Performance Summary

| Strategy | Success Rate | Avg Duration | Total Chars | Total Words | Status |
|----------|--------------|--------------|-------------|-------------|--------|
| Tesseract Local | 2/2 (100.0%) | 1545.9ms | 3,182 | 486 | ✅ Success |
| Saptiva OCR | 2/2 (100.0%) | 37307.5ms | 2,843 | 405 | ✅ Success |
| DeepSeek OCR | 0/2 (0.0%) | 497.3ms | 0 | 0 | ❌ Failed |

## Text Similarity (Accuracy)

| Comparison | Similarity |
|------------|------------|
| Tesseract Local vs Saptiva OCR | 1.13% |

## 🏆 Best Performers

**Fastest**: Tesseract Local (3091.79ms total)
**Most Text Extracted**: Tesseract Local (3,182 chars)

## 💡 Recommendation

✅ **MAINTAIN Saptiva OCR** - Proven reliability in production

## Detailed Results per Page

### Tesseract Local

| Page | Chars | Words | Duration | Status |
|------|-------|-------|----------|--------|
| 1 | 295 | 37 | 729.89ms | ✅ |
| 2 | 2887 | 449 | 2338.81ms | ✅ |

### Saptiva OCR

| Page | Chars | Words | Duration | Status |
|------|-------|-------|----------|--------|
| 1 | 237 | 19 | 0ms | ✅ |
| 2 | 2606 | 386 | 0ms | ✅ |

### DeepSeek OCR

| Page | Chars | Words | Duration | Status |
|------|-------|-------|----------|--------|
| 1 | 0 | 0 | 546.31ms | ❌ Server error '503 Service Unavailable' for url 'https://saptivadev1-deepseek-ocr-space.hf.space/ocr'
For more information check: https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/503 |
| 2 | 0 | 0 | 447.51ms | ❌ Server error '503 Service Unavailable' for url 'https://saptivadev1-deepseek-ocr-space.hf.space/ocr'
For more information check: https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/503 |
