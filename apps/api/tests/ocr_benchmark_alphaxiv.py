#!/usr/bin/env python3
"""
OCR Benchmark: Saptiva OCR vs DeepSeek OCR (AlphaXiv API)

Compara dos estrategias de extracción de texto OCR usando la API oficial de AlphaXiv:
1. Saptiva OCR (producción actual)
2. DeepSeek OCR (vía AlphaXiv API oficial)

Genera reportes automáticos en JSON y Markdown con métricas cuantitativas.

Usage:
    cd apps/api
    python -m tests.ocr_benchmark_alphaxiv --pdf ../../tests/data/pdf/sample_text.pdf --pages 2
"""

import argparse
import asyncio
import difflib
import json
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional
import subprocess

import fitz  # PyMuPDF
import httpx

from src.services.document_extraction import extract_text_from_file
from src.models.document import PageContent


class OCRStrategy:
    """Base class for OCR strategies."""

    def __init__(self, name: str):
        self.name = name

    async def extract_pages(self, pdf_path: Path, page_numbers: List[int]) -> Dict[str, Any]:
        """
        Extract text from specified pages.

        Returns:
            {
                "success": bool,
                "pages": List[{"page": int, "text": str, "duration_ms": float}],
                "total_duration_ms": float,
                "total_chars": int,
                "total_words": int,
                "error": Optional[str]
            }
        """
        raise NotImplementedError


class SaptivaOCRStrategy(OCRStrategy):
    """Saptiva OCR (current production)."""

    def __init__(self):
        super().__init__("Saptiva OCR")

    async def extract_pages(self, pdf_path: Path, page_numbers: List[int]) -> Dict[str, Any]:
        start_time = time.time()
        pages_data = []
        total_chars = 0
        total_words = 0

        try:
            # Extract only requested pages
            doc = fitz.open(pdf_path)

            for page_num in page_numbers:
                page_start = time.time()

                try:
                    # Extract page as single-page PDF for processing
                    temp_pdf_path = Path(f"/tmp/saptiva_page_{page_num}.pdf")
                    single_page_doc = fitz.open()
                    single_page_doc.insert_pdf(doc, from_page=page_num - 1, to_page=page_num - 1)
                    single_page_doc.save(str(temp_pdf_path))
                    single_page_doc.close()

                    # Use production extraction pipeline
                    page_contents = await extract_text_from_file(
                        file_path=temp_pdf_path,
                        content_type="application/pdf"
                    )

                    text = "\n\n".join([p.text_md for p in page_contents])
                    text = text.strip()

                    duration = (time.time() - page_start) * 1000
                    chars = len(text)
                    words = len(text.split())

                    pages_data.append({
                        "page": page_num,
                        "text": text,
                        "duration_ms": duration,
                        "chars": chars,
                        "words": words,
                    })

                    total_chars += chars
                    total_words += words

                except Exception as page_error:
                    pages_data.append({
                        "page": page_num,
                        "text": "",
                        "duration_ms": 0,
                        "chars": 0,
                        "words": 0,
                        "error": str(page_error),
                    })

            doc.close()

            total_duration = (time.time() - start_time) * 1000

            return {
                "success": True,
                "pages": pages_data,
                "total_duration_ms": total_duration,
                "total_chars": total_chars,
                "total_words": total_words,
                "error": None,
            }

        except Exception as exc:
            return {
                "success": False,
                "pages": pages_data,
                "total_duration_ms": (time.time() - start_time) * 1000,
                "total_chars": total_chars,
                "total_words": total_words,
                "error": str(exc),
            }


class DeepSeekAlphaXivStrategy(OCRStrategy):
    """DeepSeek OCR via AlphaXiv official API."""

    def __init__(self, api_url: str = "https://api.alphaxiv.org/models/v1/deepseek/deepseek-ocr/inference", timeout: float = 120.0):
        super().__init__("DeepSeek OCR (AlphaXiv)")
        self.api_url = api_url
        self.timeout = timeout

    async def extract_pages(self, pdf_path: Path, page_numbers: List[int]) -> Dict[str, Any]:
        start_time = time.time()
        pages_data = []
        total_chars = 0
        total_words = 0

        try:
            doc = fitz.open(pdf_path)

            for page_num in page_numbers:
                page_start = time.time()

                try:
                    # Convert page to image
                    page = doc.load_page(page_num - 1)
                    pixmap = page.get_pixmap(dpi=150)

                    # Save as JPEG
                    temp_image_path = f"/tmp/deepseek_page_{page_num}.jpg"
                    pixmap.save(temp_image_path)

                    # Call AlphaXiv API
                    text = await self._call_alphaxiv_api(temp_image_path)

                    text = text.strip()
                    duration = (time.time() - page_start) * 1000
                    chars = len(text)
                    words = len(text.split())

                    pages_data.append({
                        "page": page_num,
                        "text": text,
                        "duration_ms": duration,
                        "chars": chars,
                        "words": words,
                    })

                    total_chars += chars
                    total_words += words

                except Exception as page_error:
                    pages_data.append({
                        "page": page_num,
                        "text": "",
                        "duration_ms": 0,
                        "chars": 0,
                        "words": 0,
                        "error": str(page_error),
                    })

            doc.close()

            total_duration = (time.time() - start_time) * 1000

            return {
                "success": True,
                "pages": pages_data,
                "total_duration_ms": total_duration,
                "total_chars": total_chars,
                "total_words": total_words,
                "error": None,
            }

        except Exception as exc:
            return {
                "success": False,
                "pages": pages_data,
                "total_duration_ms": (time.time() - start_time) * 1000,
                "total_chars": total_chars,
                "total_words": total_words,
                "error": str(exc),
            }

    async def _call_alphaxiv_api(self, image_path: str) -> str:
        """Call AlphaXiv API with retry logic."""
        max_retries = 2  # Reduced retries since timeout is generous

        for attempt in range(1, max_retries + 1):
            try:
                async with httpx.AsyncClient(timeout=self.timeout) as client:
                    with open(image_path, "rb") as f:
                        files = {"file": (Path(image_path).name, f, "image/jpeg")}

                        response = await client.post(
                            self.api_url,
                            files=files,
                        )
                        response.raise_for_status()

                        data = response.json()

                        # Extract text from response
                        if "data" in data and "ocr_text" in data["data"]:
                            return data["data"]["ocr_text"]
                        else:
                            raise ValueError(f"Unexpected API response format: {data}")

            except httpx.HTTPStatusError as exc:
                if attempt == max_retries:
                    raise Exception(f"AlphaXiv API error: {exc.response.status_code} {exc.response.text}")
                await asyncio.sleep(2 ** attempt)

            except Exception as exc:
                if attempt == max_retries:
                    raise
                await asyncio.sleep(2 ** attempt)

        return ""


class OCRBenchmark:
    """Orchestrates OCR benchmark execution and reporting."""

    def __init__(self, output_dir: Path):
        self.output_dir = output_dir
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def generate_comparison_metrics(self, results: Dict[str, Any]) -> Dict[str, Any]:
        """Generate comparison metrics between strategies."""
        comparison = {
            "text_similarities": {},
            "best_speed": None,
            "best_extraction": None,
        }

        # Calculate text similarity between strategies
        strategy_texts = {}
        for strategy, data in results.items():
            if data["success"] and data["pages"]:
                combined_text = " ".join([p["text"] for p in data["pages"]])
                strategy_texts[strategy] = combined_text

        # Pairwise similarity
        strategies = list(strategy_texts.keys())
        for i, strategy1 in enumerate(strategies):
            for strategy2 in strategies[i + 1 :]:
                text1 = strategy_texts[strategy1]
                text2 = strategy_texts[strategy2]
                similarity = difflib.SequenceMatcher(None, text1, text2).ratio() * 100
                comparison["text_similarities"][f"{strategy1}_vs_{strategy2}"] = round(similarity, 2)

        # Find best speed
        speed_ranking = sorted(
            [(s, d["total_duration_ms"]) for s, d in results.items() if d["success"]],
            key=lambda x: x[1],
        )
        if speed_ranking:
            comparison["best_speed"] = {
                "strategy": speed_ranking[0][0],
                "duration_ms": round(speed_ranking[0][1], 2),
            }

        # Find best extraction (most characters)
        extraction_ranking = sorted(
            [(s, d["total_chars"]) for s, d in results.items() if d["success"]],
            key=lambda x: x[1],
            reverse=True,
        )
        if extraction_ranking:
            comparison["best_extraction"] = {
                "strategy": extraction_ranking[0][0],
                "total_chars": extraction_ranking[0][1],
            }

        return comparison

    def generate_markdown_report(self, benchmark_data: Dict[str, Any]) -> str:
        """Generate human-readable Markdown report."""
        results = benchmark_data["results"]
        comparison = benchmark_data["comparison"]
        metadata = benchmark_data["metadata"]

        md = [
            "# 📊 OCR Benchmark Report (AlphaXiv)",
            "",
            f"**Generated**: {metadata['timestamp']}",
            f"**PDF**: {metadata['pdf_path']}",
            f"**Pages Tested**: {metadata['pages_tested']}",
            "",
            "## Performance Summary",
            "",
            "| Strategy | Success Rate | Avg Duration | Total Chars | Total Words | Status |",
            "|----------|--------------|--------------|-------------|-------------|--------|",
        ]

        for strategy, data in results.items():
            success_count = len([p for p in data["pages"] if "error" not in p])
            total_pages = len(data["pages"])
            success_rate = (success_count / total_pages * 100) if total_pages > 0 else 0
            avg_duration = data["total_duration_ms"] / success_count if success_count > 0 else 0
            status = "✅ Success" if data["success"] else f"❌ Failed ({data['error']})"

            md.append(
                f"| {strategy} | {success_count}/{total_pages} ({success_rate:.1f}%) | "
                f"{avg_duration:.1f}ms | {data['total_chars']:,} | {data['total_words']} | {status} |"
            )

        md.append("")
        md.append("## Text Similarity (Accuracy)")
        md.append("")
        md.append("| Comparison | Similarity |")
        md.append("|------------|------------|")

        for comparison_key, similarity in comparison["text_similarities"].items():
            md.append(f"| {comparison_key.replace('_vs_', ' vs ')} | {similarity}% |")

        md.append("")
        md.append("## 🏆 Best Performers")
        md.append("")

        if comparison["best_speed"]:
            md.append(
                f"**Fastest**: {comparison['best_speed']['strategy']} "
                f"({comparison['best_speed']['duration_ms']}ms total)"
            )

        if comparison["best_extraction"]:
            md.append(
                f"**Most Text Extracted**: {comparison['best_extraction']['strategy']} "
                f"({comparison['best_extraction']['total_chars']:,} chars)"
            )

        md.append("")
        md.append("## 💡 Recommendation")
        md.append("")

        # Determine recommendation based on similarity and performance
        if comparison["text_similarities"]:
            similarity_value = list(comparison["text_similarities"].values())[0]
            if similarity_value > 85:
                md.append("✅ **HIGH SIMILARITY** - Both strategies produce comparable results")
            elif similarity_value > 70:
                md.append("⚠️ **MODERATE SIMILARITY** - Review differences manually")
            else:
                md.append("❌ **LOW SIMILARITY** - Strategies produce significantly different results")

        # Detailed per-page results
        md.append("")
        md.append("## Detailed Results per Page")
        md.append("")

        for strategy, data in results.items():
            md.append(f"### {strategy}")
            md.append("")
            md.append("| Page | Chars | Words | Duration | Status |")
            md.append("|------|-------|-------|----------|--------|")

            for page_data in data["pages"]:
                status = "✅" if "error" not in page_data else f"❌ {page_data['error']}"
                md.append(
                    f"| {page_data['page']} | {page_data['chars']} | {page_data['words']} | "
                    f"{page_data['duration_ms']:.2f}ms | {status} |"
                )

            md.append("")

        return "\n".join(md)

    async def run(self, pdf_path: Path, page_numbers: List[int], deepseek_timeout: float = 120.0) -> Dict[str, Any]:
        """Run complete OCR benchmark."""
        print("\n" + "=" * 70)
        print("🔬 OCR BENCHMARK (AlphaXiv)")
        print("=" * 70)
        print(f"\nPDF: {pdf_path.name}")
        print(f"Pages: {page_numbers}")
        print(f"DeepSeek Timeout: {deepseek_timeout}s")
        print(f"Output: {self.output_dir}\n")

        # Initialize strategies
        strategies = [
            SaptivaOCRStrategy(),
            DeepSeekAlphaXivStrategy(timeout=deepseek_timeout),
        ]

        # Run each strategy
        results = {}
        for strategy in strategies:
            print(f"📋 Running {strategy.name}...")
            result = await strategy.extract_pages(pdf_path, page_numbers)

            if result["success"]:
                print(f"   ✅ Success: {result['total_chars']:,} chars in {result['total_duration_ms']:.0f}ms")
            else:
                print(f"   ❌ Failed: {result['error']}")

            results[strategy.name] = result

        print("")

        # Generate comparison metrics
        comparison = self.generate_comparison_metrics(results)

        # Create benchmark data
        benchmark_data = {
            "metadata": {
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "pdf_path": str(pdf_path),
                "pages_tested": page_numbers,
                "api_provider": "AlphaXiv",
            },
            "results": results,
            "comparison": comparison,
        }

        # Save JSON report
        json_path = self.output_dir / "ocr_benchmark_alphaxiv.json"
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(benchmark_data, f, indent=2, ensure_ascii=False)
        print(f"💾 JSON report: {json_path}")

        # Save Markdown report
        md_report = self.generate_markdown_report(benchmark_data)
        md_path = self.output_dir / "ocr_benchmark_alphaxiv.md"
        with open(md_path, "w", encoding="utf-8") as f:
            f.write(md_report)
        print(f"💾 Markdown report: {md_path}")

        # Print summary
        print("\n" + "=" * 70)
        print("📊 BENCHMARK SUMMARY")
        print("=" * 70)

        for strategy, data in results.items():
            success_count = len([p for p in data["pages"] if "error" not in p])
            total_pages = len(data["pages"])
            print(f"\n{strategy}:")
            print(f"  Success: {success_count}/{total_pages}")
            print(f"  Duration: {data['total_duration_ms']:.0f}ms")
            print(f"  Characters: {data['total_chars']:,}")

        if comparison["text_similarities"]:
            print("\nText Similarity:")
            for comp, similarity in comparison["text_similarities"].items():
                print(f"  {comp.replace('_vs_', ' vs ')}: {similarity}%")

        print("\n" + "=" * 70)

        return benchmark_data


def parse_pages(pages_str: str) -> List[int]:
    """Parse page numbers from string (e.g., '1,2,3' or '1-3')."""
    pages = []
    for part in pages_str.split(","):
        if "-" in part:
            start, end = map(int, part.split("-"))
            pages.extend(range(start, end + 1))
        else:
            pages.append(int(part))
    return sorted(set(pages))


async def main():
    parser = argparse.ArgumentParser(description="OCR Benchmark: Saptiva vs DeepSeek (AlphaXiv)")
    parser.add_argument("--pdf", type=Path, required=True, help="Path to PDF file")
    parser.add_argument("--pages", type=str, default="1,2", help="Pages to test (e.g., '1,2,3' or '1-3')")
    parser.add_argument("--output", type=Path, default=Path("tests/reports"), help="Output directory")
    parser.add_argument("--deepseek-timeout", type=float, default=180.0, help="Timeout for DeepSeek API calls in seconds (default: 180)")

    args = parser.parse_args()

    if not args.pdf.exists():
        print(f"❌ PDF not found: {args.pdf}")
        return 1

    page_numbers = parse_pages(args.pages)

    benchmark = OCRBenchmark(output_dir=args.output)
    await benchmark.run(
        pdf_path=args.pdf,
        page_numbers=page_numbers,
        deepseek_timeout=args.deepseek_timeout
    )

    return 0


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    exit(exit_code)
