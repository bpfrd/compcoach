import json
import time
from typing import TYPE_CHECKING, Any

import httpx
from openai import OpenAI

from compcoach.config import OPENAI_API_KEY, OPENAI_BASE_URL, OPENAI_MODEL
from compcoach.rag.retriever import CourseRetriever

if TYPE_CHECKING:
    from compcoach.audit import AuditLogger

SEARCH_COURSES_TOOL = {
    "type": "function",
    "function": {
        "name": "search_courses",
        "description": (
            "Search the course catalog when the user wants course recommendations or "
            "structured learning resources. Use a focused natural-language query."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Search query, e.g. 'ethical AI attitudes for educators'",
                },
                "domain": {
                    "type": "string",
                    "enum": ["digital_competences", "ai_competences"],
                    "description": "Optional filter by competence domain",
                },
                "area": {
                    "type": "string",
                    "description": "Optional competency area slug, e.g. ethics, professional_engagement",
                },
                "dimension": {
                    "type": "string",
                    "enum": ["attitude", "behaviour", "knowledge", "skill"],
                    "description": "Optional filter by competence dimension",
                },
                "n_results": {
                    "type": "integer",
                    "description": "Number of courses to retrieve (default 4)",
                },
            },
            "required": ["query"],
        },
    },
}


def _api_messages(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Only roles/content sent to the API (tool turns stay inside complete())."""
    out: list[dict[str, Any]] = []
    for msg in messages:
        role = msg.get("role")
        if role not in ("system", "user", "assistant"):
            continue
        content = msg.get("content")
        if content is None:
            continue
        out.append({"role": role, "content": str(content)})
    return out


class CoachLLM:
    def __init__(self, retriever: CourseRetriever | None = None) -> None:
        if not OPENAI_API_KEY:
            raise ValueError(
                "OPENAI_API_KEY is not set. Copy .env.example to .env and add your API key."
            )
        client_kwargs: dict = {
            "api_key": OPENAI_API_KEY,
            "timeout": httpx.Timeout(120.0, connect=15.0),
        }
        if OPENAI_BASE_URL:
            client_kwargs["base_url"] = OPENAI_BASE_URL
        self.client = OpenAI(**client_kwargs)
        self.model = OPENAI_MODEL
        self._retriever = retriever

    @property
    def retriever(self) -> CourseRetriever:
        if self._retriever is None:
            self._retriever = CourseRetriever()
        return self._retriever

    def _run_tool(
        self,
        name: str,
        arguments: str,
        audit: "AuditLogger | None" = None,
        *,
        username: str | None = None,
        chat_id: int | None = None,
        turn_number: int | None = None,
    ) -> str:
        if name != "search_courses":
            return json.dumps({"error": f"Unknown tool: {name}"})
        try:
            args = json.loads(arguments) if arguments else {}
        except json.JSONDecodeError:
            return json.dumps({"error": "Invalid tool arguments JSON"})
        t0 = time.perf_counter()
        hits = self.retriever.search(
            query=args.get("query", ""),
            n_results=args.get("n_results", 4),
            domain=args.get("domain"),
            area=args.get("area"),
            dimension=args.get("dimension"),
        )
        tool_ms = int((time.perf_counter() - t0) * 1000)
        if audit and username:
            audit.log_search_courses(
                username=username,
                chat_id=chat_id,
                turn_number=turn_number,
                query=args.get("query", ""),
                domain=args.get("domain"),
                area=args.get("area"),
                dimension=args.get("dimension"),
                results_count=len(hits),
                course_slugs=[h.get("slug", "") for h in hits],
                tool_latency_ms=tool_ms,
            )
        return json.dumps(
            {"courses": hits, "formatted": self.retriever.format_for_prompt(hits)},
            indent=2,
        )

    def complete(
        self,
        messages: list[dict[str, Any]],
        *,
        max_tool_rounds: int = 2,
        audit: "AuditLogger | None" = None,
        username: str | None = None,
        chat_id: int | None = None,
        turn_number: int | None = None,
        is_opening: bool = False,
    ) -> str:
        """Run chat completion with optional tool calls for course RAG."""
        working = _api_messages(messages)
        t0 = time.perf_counter()

        for round_idx in range(max_tool_rounds + 1):
            is_final_round = round_idx == max_tool_rounds
            kwargs: dict[str, Any] = {
                "model": self.model,
                "messages": working,
            }
            if is_final_round:
                kwargs["tool_choice"] = "none"
            else:
                kwargs["tools"] = [SEARCH_COURSES_TOOL]
                kwargs["tool_choice"] = "auto"

            response = self.client.chat.completions.create(**kwargs)
            choice = response.choices[0].message

            if choice.tool_calls and not is_final_round:
                tool_calls_payload = [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.function.name,
                            "arguments": tc.function.arguments or "{}",
                        },
                    }
                    for tc in choice.tool_calls
                ]
                assistant_msg: dict[str, Any] = {
                    "role": "assistant",
                    "tool_calls": tool_calls_payload,
                }
                if choice.content:
                    assistant_msg["content"] = choice.content
                else:
                    assistant_msg["content"] = None
                working.append(assistant_msg)

                for tc in choice.tool_calls:
                    result = self._run_tool(
                        tc.function.name,
                        tc.function.arguments or "{}",
                        audit,
                        username=username,
                        chat_id=chat_id,
                        turn_number=turn_number,
                    )
                    working.append(
                        {
                            "role": "tool",
                            "tool_call_id": tc.id,
                            "content": result,
                        }
                    )
                continue

            text = (choice.content or "").strip()
            if text:
                total_ms = int((time.perf_counter() - t0) * 1000)
                if audit and username and chat_id is not None and turn_number is not None:
                    audit.log_assistant_message(
                        username=username,
                        chat_id=chat_id,
                        turn_number=turn_number,
                        content=text,
                        llm_latency_ms=total_ms,
                        is_opening=is_opening,
                    )
                return text
            if is_final_round:
                break

        return "I couldn't generate a reply. Please try again or rephrase your question."
