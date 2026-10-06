"""Async Tev1 chunk classification using document-specific decision criteria."""
import httpx
from pydantic import BaseModel, Field

from backend.app.core.config import Settings
from backend.app.models import DocumentType


ASSESSMENT_QUESTIONS = {
    "component_type": {
        "type": "choice",
        "instructions": "Classify the semantic role of this extracted assessment text.",
        "criteria": {
            "assessment_metadata": (
                "Administrative and identifying information about the assessment. "
                "This includes the component or course code and name, assessment or "
                "assignment title, weighting, total marks, issue date or week, due date "
                "or submission deadline, and similar assessment-level details. "
                "This content describes the assessment itself rather than work the "
                "student must perform."
            ),

            "assessment_task": (
                "A task, question, activity, problem, or set of academic requirements "
                "that the student must complete or demonstrate as part of the assessment. "
                "This includes sections such as Task 1, Task 2, Question 1, Question 2, "
                "and their associated requirements."
            ),

            "assessment_summary": (
                "A high-level description of the assessment, including its purpose, "
                "scenario, context, overall objectives, or a summary of the work that "
                "students are expected to complete. This includes sections such as "
                "Brief or Problem Statement."
            ),

            "assessment_instruction": (
                "Procedural guidance describing how the assessment should be completed "
                "or submitted. This includes file naming, submission format, required "
                "software, programming conventions, referencing requirements, submission "
                "structure, presentation requirements, and similar instructions."
            ),

            "assessment_criteria": (
                "Information describing how student work will be evaluated or graded. "
                "This includes marking criteria, grading categories, rubric descriptions, "
                "performance expectations, and marks or percentage allocations associated "
                "with evaluation criteria."
            ),

            "other": (
                "Content that does not clearly belong to assessment metadata, assessment "
                "tasks, assessment summary, assessment instructions, or assessment criteria. "
                "This may include academic integrity statements, copyright notices, headers, "
                "footers, policies, and unrelated administrative content."
            )
        }
    },
}
OVERVIEW_QUESTIONS = {
    "component_type": {
        "type": "choice",
        "instructions": (
            "Classify this extracted paper or course text by its primary semantic "
            "role in the component document. Choose the category that best represents "
            "the purpose of the text, not only the wording of its heading."
        ),
        "criteria": {
            "paper_metadata": (
                "Administrative and identifying information about the paper, course, "
                "or component. This includes the component code and name, NZQA level, "
                "credits, total workload, duration, and similar component-level details. "
                "This information describes the paper itself rather than its learning "
                "content, outcomes, or assessments."
            ),

            "learning_outcome": (
                "Statements describing the knowledge, skills, capabilities, or "
                "competencies that students are expected to achieve or demonstrate "
                "after successfully completing the paper or component. This includes "
                "the Learning Outcomes section and individual learning outcome statements."
            ),

            "paper_summary": (
                "A high-level description of the paper or component, including its "
                "purpose, aims, subject focus, intended learning experience, or overall "
                "description of what students will learn. This includes sections such "
                "as Component Description and Aims."
            ),

            "paper_content_and_engagement": (
                "Information describing what students will study and how they are "
                "expected to engage with the paper. This includes expected study hours, "
                "class participation, contact hours, independent study, learning "
                "activities, topic coverage, and subject content. This includes sections "
                "such as Workload and Engagement and Content Outline."
            ),

            "assessment_overview": (
                "High-level information about the assessments within the paper. This "
                "includes assessment names, weightings, issue dates, due dates, and "
                "summaries of what each assessment involves. This includes sections "
                "such as Assignments and Assignment Overviews."
            ),

            "other": (
                "Content that does not primarily belong to paper metadata, learning "
                "outcomes, paper summary, paper content and engagement, or assessment "
                "overview. This may include grading scales, recommended learning "
                "resources, submission policies, academic policies, document headers, "
                "footers, copyright information, and other supporting or administrative "
                "content."
            ),
        },
    }
}

class DecisionResult(BaseModel):
    choice: str
    confidence: float = Field(ge=0, le=1)
    probabilities: dict[str, float]


def classification_questions(document_type: DocumentType) -> dict:
    if document_type == DocumentType.COMPONENT_OVERVIEW:
        return OVERVIEW_QUESTIONS
    return ASSESSMENT_QUESTIONS


class DecisionClassifier:
    def __init__(self, settings: Settings):
        self.settings = settings
        headers = {}
        if settings.decision_api_key and settings.decision_api_key.get_secret_value():
            headers['Authorization'] = 'Bearer ' + settings.decision_api_key.get_secret_value()
        self.client = httpx.AsyncClient(timeout=settings.decision_timeout_seconds, headers=headers)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        await self.client.aclose()

    async def classify(self, text: str, document_type: DocumentType) -> DecisionResult:
        questions = classification_questions(document_type)
        response = await self.client.post(self.settings.decision_base_url, json={
            'model': self.settings.decision_model, 'state': text,
            'questions': questions, 'keep_alive': self.settings.decision_keep_alive,
        })
        response.raise_for_status()
        result = DecisionResult.model_validate(response.json()['answers']['component_type'])
        allowed = questions['component_type']['criteria']
        if result.choice not in allowed or not set(result.probabilities).issubset(allowed):
            raise ValueError('Decision model returned an unsupported classification')
        if any(not 0 <= probability <= 1 for probability in result.probabilities.values()):
            raise ValueError('Decision model returned invalid probabilities')
        return result
