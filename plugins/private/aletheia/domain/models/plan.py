from pydantic import BaseModel
from typing import List

class ResearchSubTask(BaseModel):
    id: str
    query: str
    sources: List[str] = ["web"] # e.g., web, pdf, etc.
    completed: bool = False

class ResearchPlan(BaseModel):
    main_query: str
    sub_tasks: List[ResearchSubTask] = []
