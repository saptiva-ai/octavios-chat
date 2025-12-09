import os
import requests
from typing import Dict, Any

class SaptivaModelAdapter:
    def __init__(self):
        self.api_key = os.getenv("SAPTIVA_API_KEY")
        self.base_url = os.getenv("SAPTIVA_BASE_URL", "https://api.saptiva.com/v1")
        
        if not self.api_key or self.api_key == "pon_tu_api_key_aqui":
            print("Warning: SAPTIVA_API_KEY not set. Using mock responses.")
            self.mock_mode = True
        else:
            self.mock_mode = False

    def generate(self, model: str, prompt: str, **kwargs: Any) -> Dict:
        """
        Generates a response from a Saptiva model.
        """
        print(f"--- Calling Saptiva Model: {model} ---")
        print(f"--- Prompt ---\n{prompt}")
        print("------------------------------------")

        if self.mock_mode:
            return self._get_mock_response(model, prompt)

        try:
            return self._call_real_api(model, prompt, **kwargs)
        except Exception as e:
            print(f"Error calling Saptiva API: {e}. Falling back to mock response.")
            return self._get_mock_response(model, prompt)

    def _call_real_api(self, model: str, prompt: str, **kwargs: Any) -> Dict:
        """
        Makes the actual API call to Saptiva.
        """
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        
        payload = {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": kwargs.get("max_tokens", 2000),
            "temperature": kwargs.get("temperature", 0.7)
        }
        
        # Build URL correctly, avoiding double slashes
        url = f"{self.base_url.rstrip('/')}/chat/completions"

        # Use longer timeout for LLM responses
        timeout = int(os.getenv("SAPTIVA_TIMEOUT", "120"))

        response = requests.post(
            url,
            headers=headers,
            json=payload,
            timeout=timeout
        )
        
        response.raise_for_status()
        api_response = response.json()
        
        # Extract content from the API response
        content = api_response.get("choices", [{}])[0].get("message", {}).get("content", "")
        
        return {"content": content}


    def _get_mock_response(self, model: str, prompt: str) -> Dict:
        model_name = model.lower()
        if "planner" in model_name or "ops" in model_name:
            return {
                "content": """
- id: T01
  query: "Historia y evolución de la banca abierta en México"
  sources: ["web"]
- id: T02
  query: "Principales competidores y jugadores en el ecosistema de banca abierta en México"
  sources: ["web"]
- id: T03
  query: "Regulación y marco normativo de la banca abierta en México (Ley Fintech)"
  sources: ["web"]
"""
            }
        elif "writer" in model_name or "cortex" in model_name:
            return {
                "content": "# Reporte de Investigación: Banca Abierta en México\n\n## Introducción\nLa banca abierta en México ha emergido como una fuerza transformadora en el sector financiero... (Este es un reporte mockeado)"
            }
        else:
            return {"content": "Respuesta mockeada."}
