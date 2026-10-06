from typing import Protocol
from backend.app.core.config import Settings
from backend.app.schemas.coverage import BatchJudgment
import json
import re
from ollama import AsyncClient, ResponseError
from pydantic import ValidationError
import httpx

def explicitly_references(requirement, outcome):
    # Match LO1, LO 1, and lo_1, without confusing LO1 with LO10.
    label = re.fullmatch(r'lo[\s_]*(\d+)', outcome.label or '', re.I)
    if not label:
        return False
    return any(int(n) == int(label.group(1)) for n in re.findall(r'\blo[\s_]*(\d+)\b', requirement.content, re.I))


def batch_messages(requirements, outcomes, eligible_pairs):
    compact = lambda item: {'id': str(item.id), 'label': item.label, 'content': item.content}
    return [
        {
            "role": "system",
            "content": (
                "You are analyzing assessment coverage. "
                "For each assessment requirement, determine which eligiblelearning outcomes it provides evidence toward.\n"
                "Compare the meaning of the requirement with the meaning of each eligible learning outcome. Create a match only when completing the requirement necessarily produces assessable evidence of the learning outcome. Shared topics, terminology, background knowledge, or possible student approaches are insufficient to establish a relationship.\n"

                "Classification rules:\n"
                "- addresses: the requirement strongly demonstrates the "
                "learning outcome or most of its intent.\n"
                "- partially_addresses: only when the requirement explicitly assesses a distinct part of that skill. Otherwise, omit the match. Prefer no match over a speculative relationship. "
                "- uncertain: there may be a relationship, but the provided "
                "text is insufficient to decide confidently.\n"
                "- If there is no meaningful relationship with any eligible "
                "outcome, set no_match=true.\n\n"

                "A requirement may match multiple learning outcomes. "
                "Do not require identical wording. Consider semantic meaning, "
                "skills, actions, and evidence expected from the student. "
                "Do not create a match solely because the requirement mentions "
                "an LO label such as LO1.\n\n"

                "For every match, provide a concise rationale explaining "
                "why the requirement demonstrates that learning outcome. "
                "Use only the supplied IDs."
            ),

        },
        {
            "role": "user",
            "content": json.dumps(
                {
                    "learning_outcomes": [
                        compact(outcome)
                        for outcome in outcomes
                    ],
                    "assessment_requirements": [
                        compact(requirement)
                        for requirement in requirements
                    ],
                    'eligible_outcomes': {str(r.id): [str(o.id) for o in outcomes if (r.id, o.id) in eligible_pairs] for r in requirements},
                    'explicit_references': [{'requirement_id': str(r.id), 'outcome_id': str(o.id)}
                                    for r in requirements for o in outcomes if (r.id, o.id) in eligible_pairs and explicitly_references(r, o)],
                },
                ensure_ascii=False,
            ),
        },
    ]

def output_token_limit(pair_count, requirement_count):
    return min(4096, max(512, 128 * pair_count + 64 * requirement_count))


class PairJudge(Protocol):
    async def judge_batch(self, requirements, outcomes, eligible_pairs) -> BatchJudgment: ...
    
class OllamaPairJudge:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.client = None
        self.token_budget = 16384
        self.last_usage = {}

    async def close(self):
        if self.client is not None:
            await self.client.close()
            self.client = None

    async def judge_batch(self, requirements, outcomes, eligible_pairs):
        self.last_usage = {}
        if self.settings.llm_provider != 'ollama' or not self.settings.llm_model:
            raise RuntimeError('Configure an Ollama LLM model for coverage analysis')
        if self.client is None:
            # The native Ollama client calls /api/chat, whereas chat uses /v1/chat/completions.
            host = self.settings.llm_base_url.rstrip('/').removesuffix('/v1')
            self.client = AsyncClient(host=host or 'http://host.docker.internal:11434', timeout=120)
        response = await self.client.chat(
            model=self.settings.llm_model, format=BatchJudgment.model_json_schema(), think=False,
            options={'temperature': 0, 'num_ctx': self.token_budget,
                     'num_predict': output_token_limit(len(eligible_pairs), len(requirements))},
            messages=batch_messages(requirements, outcomes, eligible_pairs),
        )
        self.last_usage = {'prompt_tokens': response.prompt_eval_count, 'output_tokens': response.eval_count}
        if response.done_reason == 'length':
            raise ValueError('Model output was truncated; retry a smaller batch')
        return BatchJudgment.model_validate_json(response.message.content or '')


def get_pair_judge(settings: Settings) -> PairJudge:
    return OllamaPairJudge(settings)

def judgment_error(exc: Exception) -> str:
    if isinstance(exc, ResponseError):
        return f'Ollama returned HTTP {exc.status_code}; check the server URL, model, and server logs'
    if isinstance(exc, httpx.TimeoutException):
        return 'Ollama request timed out; manual review or retry required'
    if isinstance(exc, (ConnectionError, httpx.ConnectError)):
        return 'Cannot connect to Ollama; check LLM_BASE_URL and that the server is running'
    if isinstance(exc, ValidationError):
        return 'LLM response did not match the required judgment schema; manual review required'
    if isinstance(exc, ValueError):
        return str(exc)
    return f'Pair judgment failed ({type(exc).__name__}); manual review required'
