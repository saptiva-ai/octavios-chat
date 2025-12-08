import os
import yaml
from typing import List
from domain.models.plan import ResearchPlan, ResearchSubTask
from adapters.saptiva_model.saptiva_client import SaptivaModelAdapter

class PlannerService:
    def __init__(self):
        self.model_adapter = SaptivaModelAdapter()
        # As per README, Planner uses 'Saptiva Ops'
        self.planner_model = os.getenv("SAPTIVA_MODEL_PLANNER", "Saptiva Ops")

    def create_plan(self, query: str) -> ResearchPlan:
        """
        Generates a research plan based on the user's query.
        """
        prompt = self._build_prompt(query)
        
        response = self.model_adapter.generate(
            model=self.planner_model,
            prompt=prompt
        )
        
        plan_yaml = response.get("content", "")
        return self._parse_plan(query, plan_yaml)

    def _build_prompt(self, query: str) -> str:
        return f"""
Based on the following user query, please generate a research plan with a list of sub-tasks in YAML format.
Each sub-task should have an 'id', a 'query', and a list of 'sources'.

User Query: "{query}"

Research Plan (YAML):
"""

    def _parse_plan(self, main_query: str, plan_yaml: str) -> ResearchPlan:
        try:
            sub_tasks_data = yaml.safe_load(plan_yaml)
            if not isinstance(sub_tasks_data, list):
                print(f"Warning: Planner did not return a list of sub-tasks. Got: {sub_tasks_data}")
                return ResearchPlan(main_query=main_query, sub_tasks=[])

            sub_tasks = [ResearchSubTask(**task_data) for task_data in sub_tasks_data]
            return ResearchPlan(main_query=main_query, sub_tasks=sub_tasks)
        except (yaml.YAMLError, TypeError) as e:
            print(f"Error parsing plan YAML: {e}")
            # Return a plan with a single task to research the original query
            return ResearchPlan(
                main_query=main_query,
                sub_tasks=[ResearchSubTask(id="T01", query=main_query, sources=["web"])]
            )
