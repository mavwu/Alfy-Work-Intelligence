import json
import re
import urllib.error
import urllib.request
from abc import ABC, abstractmethod
from typing import Any

from pydantic import BaseModel, ValidationError

from ..config import OLLAMA_URL


class AIUnavailable(Exception):
    pass


class AIProvider(ABC):
    @abstractmethod
    def health_check(self) -> dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    def list_models(self) -> list[str]:
        raise NotImplementedError

    @abstractmethod
    def generate_text(self, model: str, prompt: str, system: str = "") -> str:
        raise NotImplementedError

    def generate_structured(self, model: str, prompt: str, schema: type[BaseModel], system: str = "") -> BaseModel:
        schema_prompt = (
            f"{prompt}\n\nReturn only valid JSON matching this schema name: {schema.__name__}. "
            "Do not include markdown fences or commentary."
        )
        raw = self.generate_text(model, schema_prompt, system=system)
        data = parse_json_object(raw)
        try:
            return schema.model_validate(data)
        except ValidationError:
            repaired = self.generate_text(
                model,
                f"Repair this malformed JSON for schema {schema.__name__}. Return JSON only.\n\n{raw}",
                system=system,
            )
            return schema.model_validate(parse_json_object(repaired))


class OllamaProvider(AIProvider):
    def __init__(self, base_url: str = OLLAMA_URL):
        self.base_url = base_url.rstrip("/")

    def _request(self, path: str, payload: dict[str, Any] | None = None, timeout: int = 20) -> dict[str, Any]:
        url = f"{self.base_url}{path}"
        data = None if payload is None else json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return json.loads(response.read().decode("utf-8"))
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            raise AIUnavailable(str(exc)) from exc

    def health_check(self) -> dict[str, Any]:
        try:
            models = self.list_models()
            return {"available": True, "models": models, "message": "Ollama is reachable."}
        except AIUnavailable as exc:
            return {"available": False, "models": [], "message": f"Ollama unavailable: {exc}"}

    def list_models(self) -> list[str]:
        data = self._request("/api/tags", timeout=4)
        return [item.get("name", "") for item in data.get("models", []) if item.get("name")]

    def generate_text(self, model: str, prompt: str, system: str = "") -> str:
        if not model:
            raise AIUnavailable("No Ollama model is selected.")
        data = self._request(
            "/api/generate",
            {"model": model, "prompt": prompt, "system": system, "stream": False},
            timeout=120,
        )
        return data.get("response", "").strip()


def parse_json_object(text: str) -> Any:
    cleaned = text.strip()
    cleaned = re.sub(r"^```(?:json)?", "", cleaned).strip()
    cleaned = re.sub(r"```$", "", cleaned).strip()
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        match = re.search(r"(\{.*\}|\[.*\])", cleaned, flags=re.S)
        if not match:
            raise
        return json.loads(match.group(1))
