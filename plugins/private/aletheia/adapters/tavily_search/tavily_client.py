import os
from tavily import TavilyClient
from typing import List, Dict

class TavilySearchAdapter:
    def __init__(self):
        self.api_key = os.getenv("TAVILY_API_KEY")
        if not self.api_key or self.api_key == "pon_tu_api_key_aqui":
            raise ValueError("TAVILY_API_KEY environment variable not set or is a placeholder.")
        self.client = TavilyClient(api_key=self.api_key)

    def search(self, query: str, max_results: int = 5) -> List[Dict]:
        """
        Performs a search using the Tavily API.
        """
        try:
            response = self.client.search(query=query, search_depth="advanced", max_results=max_results)
            return response.get("results", [])
        except Exception as e:
            print(f"Error during Tavily search: {e}")
            return []
