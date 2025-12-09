from fastapi import FastAPI, BackgroundTasks, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import uuid
import time
import os
from dotenv import load_dotenv
from datetime import datetime

# Load environment variables from .env file
load_dotenv()

# Domain Services
from domain.services.planner_svc import PlannerService
from domain.services.research_svc import ResearchService
from domain.services.writer_svc import WriterService
from domain.services.iterative_research_svc import IterativeResearchOrchestrator

# Application startup time for uptime calculation
APP_START_TIME = datetime.utcnow()
API_VERSION = "v1alpha1"

app = FastAPI(
    title="Aletheia Deep Research API",
    description="API para análisis e investigación profunda con Web Search.",
    version=API_VERSION,
)

# CORS Configuration
cors_origins = os.getenv("CORS_ALLOW_ORIGINS", "http://localhost:3000").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Data Models ---

from typing import Optional

class ResearchRequest(BaseModel):
    query: str
    scope: Optional[str] = None
    budget: Optional[float] = None

class DeepResearchRequest(BaseModel):
    query: str
    scope: Optional[str] = None
    max_iterations: Optional[int] = 3
    min_completion_score: Optional[float] = 0.75
    budget: Optional[int] = 100

class WebSearchRequest(BaseModel):
    query: str
    allowed_domains: Optional[list[str]] = None
    blocked_domains: Optional[list[str]] = None
    max_uses: Optional[int] = 6
    max_depth: Optional[int] = 2
    locale: Optional[str] = "es"
    time_window: Optional[str] = None  # e.g., "month", "year"

class WebSearchSource(BaseModel):
    url: str
    title: str
    snippet: Optional[str] = None
    published_at: Optional[str] = None
    first_seen_at: str
    source_type: str = "WEB"

class WebSearchResponse(BaseModel):
    answer: str
    confidence: float  # 0.0 to 1.0
    sources: list[WebSearchSource]
    diagnostics: dict  # {fetches: int, elapsed_ms: int}

class TaskStatus(BaseModel):
    task_id: str
    status: str
    details: Optional[str] = None

class Report(BaseModel):
    status: str
    report_md: Optional[str] = None
    sources_bib: Optional[str] = None
    metrics_json: Optional[str] = None

class DeepResearchReport(BaseModel):
    status: str
    report_md: Optional[str] = None
    sources_bib: Optional[str] = None
    research_summary: Optional[dict] = None
    quality_metrics: Optional[dict] = None

class Traces(BaseModel):
    manifest_json: str
    events_ndjson: str
    otel_export_json: str

class HealthResponse(BaseModel):
    status: str
    version: str
    uptime_seconds: float
    environment: str
    services: dict

# --- In-Memory Task Store ---
tasks = {}
deep_research_tasks = {}

# --- Real Research Pipeline ---
def run_real_research_pipeline(task_id: str, query: str):
    """
    Orchestrates the research process: Plan -> Research -> Write.
    """
    tasks[task_id] = {"status": "running", "report": None}
    print(f"Starting real research for task {task_id} with query: '{query}'")

    try:
        # 1. Plan
        planner = PlannerService()
        research_plan = planner.create_plan(query)
        print(f"[{task_id}] Plan created with {len(research_plan.sub_tasks)} sub-tasks.")

        # 2. Research
        researcher = ResearchService()
        evidence_list = researcher.execute_plan(research_plan)
        print(f"[{task_id}] Research completed with {len(evidence_list)} pieces of evidence.")

        # 3. Write
        writer = WriterService()
        report_content = writer.write_report(query, evidence_list)
        print(f"[{task_id}] Report generated.")

        # 4. Store result
        tasks[task_id] = {"status": "completed", "report": report_content, "sources": "Generated from evidence"}
        print(f"Research completed for task {task_id}")

    except Exception as e:
        print(f"Error during research pipeline for task {task_id}: {e}")
        tasks[task_id] = {"status": "failed", "report": f"An error occurred: {e}"}


# --- Deep Research Pipeline (Together AI Pattern) ---
async def run_deep_research_pipeline(task_id: str, request: DeepResearchRequest):
    """
    Orchestrates the iterative deep research process using Together AI pattern.
    """
    deep_research_tasks[task_id] = {"status": "running", "result": None}
    print(f"Starting deep research for task {task_id} with query: '{request.query}'")

    try:
        # Initialize iterative research orchestrator
        orchestrator = IterativeResearchOrchestrator(
            max_iterations=request.max_iterations,
            min_completion_score=request.min_completion_score,
            budget=request.budget
        )
        
        # Execute deep research
        result = await orchestrator.execute_deep_research(request.query)
        
        # Store result
        deep_research_tasks[task_id] = {
            "status": "completed",
            "result": result,
            "summary": orchestrator.get_research_summary(result)
        }
        print(f"Deep research completed for task {task_id}")

    except Exception as e:
        print(f"Error during deep research pipeline for task {task_id}: {e}")
        deep_research_tasks[task_id] = {"status": "failed", "error": f"An error occurred: {e}"}


# --- API Endpoints ---

@app.get("/health", response_model=HealthResponse, tags=["System"])
async def health_check():
    """
    Health check endpoint - returns API status and service availability.
    """
    uptime = (datetime.utcnow() - APP_START_TIME).total_seconds()

    # Check service availability
    services = {
        "saptiva": bool(os.getenv("SAPTIVA_API_KEY")) and os.getenv("SAPTIVA_API_KEY") != "pon_tu_api_key_aqui",
        "tavily": bool(os.getenv("TAVILY_API_KEY")) and os.getenv("TAVILY_API_KEY") != "pon_tu_api_key_aqui",
        "web_search": os.getenv("WEB_SEARCH_ENABLED", "false").lower() == "true",
        "vector_store": os.getenv("VECTOR_BACKEND", "none") != "none",
        "telemetry": os.getenv("ENABLE_TELEMETRY", "false").lower() == "true"
    }

    return HealthResponse(
        status="ok",
        version=API_VERSION,
        uptime_seconds=uptime,
        environment=os.getenv("ENVIRONMENT", "development"),
        services=services
    )

@app.post("/research", status_code=status.HTTP_202_ACCEPTED, response_model=TaskStatus, tags=["Research"])
async def start_research(request: ResearchRequest, background_tasks: BackgroundTasks):
    """
    Starts a new research task.
    """
    # Check for API keys and inform the user if they are missing
    saptiva_key = os.getenv("SAPTIVA_API_KEY")
    tavily_key = os.getenv("TAVILY_API_KEY")
    
    if not saptiva_key or saptiva_key == "pon_tu_api_key_aqui":
        # The Saptiva adapter has a mock mode, so this is a soft warning.
        print("Warning: SAPTIVA_API_KEY is not set. The planner and writer will use mock data.")

    if not tavily_key or tavily_key == "pon_tu_api_key_aqui":
        # The Tavily adapter will fail, so this is a hard error for the research step.
        # The pipeline will still run but the research step will be disabled.
        print("Warning: TAVILY_API_KEY is not set. The research step will be skipped.")

    task_id = str(uuid.uuid4())
    tasks[task_id] = {"status": "accepted"}
    background_tasks.add_task(run_real_research_pipeline, task_id, request.query)
    return TaskStatus(task_id=task_id, status="accepted", details="Research task has been accepted and is running in the background.")

@app.get("/reports/{task_id}", response_model=Report, tags=["Research"])
async def get_report(task_id: str):
    """
    Retrieves the status and result of a research task.
    """
    task = tasks.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    if task["status"] == "completed":
        return Report(
            status="completed",
            report_md=task.get("report"),
            sources_bib=task.get("sources"),
            metrics_json='{"mock_metric": 1.0}'
        )
    else:
        return Report(status=task["status"], report_md=task.get("report"))


@app.get("/traces/{task_id}", response_model=Traces, tags=["Research"])
async def get_traces(task_id: str):
    """
    Retrieves traceability and observability artifacts for a task.
    """
    if task_id not in tasks:
        raise HTTPException(status_code=404, detail="Task not found")

    return Traces(
        manifest_json='{"version": "0.1.0", "seed": 123}',
        events_ndjson='{"event": "mock_event", "timestamp": "2025-09-10T21:00:00Z"}',
        otel_export_json='{"trace_id": "mock_trace_id"}',
    )


# --- Deep Research Endpoints (Together AI Pattern) ---

@app.post("/deep-research", status_code=status.HTTP_202_ACCEPTED, response_model=TaskStatus, tags=["Deep Research"])
async def start_deep_research(request: DeepResearchRequest, background_tasks: BackgroundTasks):
    """
    Starts a new iterative deep research task using Together AI pattern.
    """
    # Check for API keys
    saptiva_key = os.getenv("SAPTIVA_API_KEY")
    tavily_key = os.getenv("TAVILY_API_KEY")
    
    if not saptiva_key or saptiva_key == "pon_tu_api_key_aqui":
        print("Warning: SAPTIVA_API_KEY is not set. Some agents will use mock data.")

    if not tavily_key or tavily_key == "pon_tu_api_key_aqui":
        print("Warning: TAVILY_API_KEY is not set. Research will be limited.")

    task_id = str(uuid.uuid4())
    deep_research_tasks[task_id] = {"status": "accepted"}
    background_tasks.add_task(run_deep_research_pipeline, task_id, request)
    
    return TaskStatus(
        task_id=task_id, 
        status="accepted", 
        details=f"Deep research task accepted. Configuration: {request.max_iterations} iterations, {request.min_completion_score} min score."
    )

@app.get("/deep-research/{task_id}", response_model=DeepResearchReport, tags=["Deep Research"])
async def get_deep_research_report(task_id: str):
    """
    Retrieves the status and result of a deep research task.
    """
    task = deep_research_tasks.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Deep research task not found")

    if task["status"] == "completed":
        result = task["result"]
        summary = task["summary"]
        
        return DeepResearchReport(
            status="completed",
            report_md=result.final_report,
            sources_bib=f"Generated from {result.total_evidence_count} evidence sources",
            research_summary=summary,
            quality_metrics={
                "completion_level": result.completion_level,
                "quality_score": result.research_quality_score,
                "evidence_count": result.total_evidence_count,
                "execution_time": result.execution_time_seconds
            }
        )
    elif task["status"] == "failed":
        return DeepResearchReport(
            status="failed",
            report_md=f"Deep research failed: {task.get('error', 'Unknown error')}"
        )
    else:
        return DeepResearchReport(status=task["status"])


# --- Web Search Endpoint ---

@app.post("/web-search", response_model=WebSearchResponse, tags=["Web Search"])
async def web_search(request: WebSearchRequest):
    """
    Performs a web search and returns synthesized answer with sources.

    This endpoint orchestrates:
    1. Fetch: Search web with Tavily (respecting robots.txt and constraints)
    2. Extract: Normalize and clean search results
    3. Rank: Score sources by relevance using BM25 + embeddings
    4. Synthesize: Generate answer with exact citations using Saptiva model

    Returns answer with confidence score, sources, and diagnostics.
    """
    start_time = time.time()

    # Check if web search is enabled
    if not os.getenv("WEB_SEARCH_ENABLED", "false").lower() == "true":
        raise HTTPException(
            status_code=503,
            detail="Web search is not enabled. Set WEB_SEARCH_ENABLED=true"
        )

    # Check for Tavily API key
    tavily_key = os.getenv("TAVILY_API_KEY")
    if not tavily_key or tavily_key == "pon_tu_api_key_aqui":
        raise HTTPException(
            status_code=503,
            detail="Tavily API key not configured"
        )

    try:
        # Import web search service
        from domain.services.web_search_svc import WebSearchService

        # Initialize service
        search_service = WebSearchService()

        # Execute search with constraints
        result = await search_service.search_and_synthesize(
            query=request.query,
            allowed_domains=request.allowed_domains,
            blocked_domains=request.blocked_domains,
            max_results=request.max_uses,
            max_depth=request.max_depth,
            locale=request.locale,
            time_window=request.time_window
        )

        # Calculate elapsed time
        elapsed_ms = int((time.time() - start_time) * 1000)

        # Build response
        return WebSearchResponse(
            answer=result["answer"],
            confidence=result["confidence"],
            sources=[
                WebSearchSource(
                    url=source["url"],
                    title=source["title"],
                    snippet=source.get("snippet"),
                    published_at=source.get("published_at"),
                    first_seen_at=source["first_seen_at"],
                    source_type=source.get("source_type", "WEB")
                )
                for source in result["sources"]
            ],
            diagnostics={
                "fetches": result.get("fetches", len(result["sources"])),
                "elapsed_ms": elapsed_ms
            }
        )

    except Exception as e:
        print(f"Error during web search: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Web search failed: {str(e)}"
        )