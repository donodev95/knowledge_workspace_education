from pprint import pprint
import requests


OLLAMA_URL = "http://localhost:11434/v1/systemone"
MODEL = "tev1:0.8b"

# assessment brief criteria
state = """
Assignment One: Data cleaning and Data visualization-Report (25%)
In this assessment, students undertake two tasks, firstly a case study and write a report advising a client of any potential data mining applications they can employ in their business. Secondly, discover and explore data from the stock market time series datasets.
"""


questions = {
    "component_type": {
        "type": "choice",
        "instructions": (
            "Classify the semantic role of this extracted assessment text."
        ),
        "criteria": {
            "assessment_task": (
                "A specific task, question, activity, or group of requirements that the "
                "student must complete as part of the assessment. This includes major "
                "assessment sections such as Task 1, Task 2, Question 1, Question 2, "
                "and the detailed requirements contained within them."
            ),

            "assessment_summary": (
                "A high-level description of the assessment, including its purpose, "
                "scenario, expected work, overall objectives, or a summary of what the "
                "student is required to complete. Examples include Brief, Problem Statement, "
                "or introductory descriptions of the assessment."
            ),

            "assessment_instruction": (
                "General instructions about how the assessment should be completed or submitted, "
                "rather than the academic content being assessed. This includes submission format, "
                "file naming, required software, programming conventions, referencing requirements, "
                "submission structure, deadlines, presentation requirements, and similar procedural guidance."
            ),

            "assessment_criteria": (
                "A statement describing how the student's work will be evaluated, graded, "
                "or awarded marks. This includes assessment criteria, marking categories, "
                "percentage weightings, performance expectations, and rubric-related statements."
            ),

            "other": (
                "Content that does not clearly belong to assessment tasks, assessment summary, "
                "assessment instructions, or assessment criteria. This may include policy statements, "
                "academic integrity declarations, copyright text, document headers, footers, "
                "or unrelated administrative content."
            ),
        }
    }
}

# # Component Overview 
# questions = {
#     "component_type": {
#         "type": "choice",
#         "instructions": (
#             "Classify this extracted paper text by its primary semantic role "
#             "in the course or component document. Choose the category that "
#             "best represents the purpose of the text, not only the wording "
#             "of its heading."
#         ),
#         "criteria": {
#             "learning_outcome": (
#                 "Statements describing the knowledge, skills, capabilities, "
#                 "or competencies that students are expected to achieve or "
#                 "demonstrate after successfully completing the component. "
#                 "This includes sections such as Learning Outcomes and individual "
#                 "learning outcome statements."
#             ),

#             "paper_summarization": (
#                 "A high-level description of the component or paper, including "
#                 "its purpose, aims, subject focus, intended learning experience, "
#                 "or an overall summary of what the paper teaches. This includes "
#                 "sections such as Component Description and Aims."
#             ),

#             "paper_content_and_engagement": (
#                 "Information describing what students will study and how they "
#                 "are expected to engage with the paper. This includes workload, "
#                 "expected study hours, class participation, prescribed learning "
#                 "activities, topic coverage, subject content, and content outlines. "
#                 "Examples include Workload and Engagement and Content Outline."
#             ),

#             "assessment_overview": (
#                 "Information describing the assessments used in the paper, "
#                 "including assessment names, weightings, issue or due dates, "
#                 "assessment summaries, and high-level descriptions of what each "
#                 "assignment requires. This includes sections such as Assignments "
#                 "and Assignment Overviews."
#             ),

#             "other": (
#                 "Content that does not primarily describe learning outcomes, "
#                 "the paper summary, paper content and engagement, or assessment "
#                 "overviews. This includes component metadata, grading scales, "
#                 "recommended learning resources, submission policies, document "
#                 "headers, footers, administrative information, and other "
#                 "supporting content."
#             ),
#         },
#     }
# }

def classify_component(
    state: str,
    questions: dict,
    model: str = MODEL,
) -> dict:
    """
    Classify assessment text using the Tev1 decision model.

    Returns:
        {
            "choice": str,
            "confidence": float,
            "probabilities": dict
        }
    """

    payload = {
        "model": model,
        "state": state,
        "questions": questions,
        "keep_alive": "10m",
    }

    response = requests.post(
        OLLAMA_URL,
        json=payload,
        timeout=120,
    )

    response.raise_for_status()

    data = response.json()

    answer = data["answers"]["component_type"]

    return {
        "choice": answer["choice"],
        "confidence": answer["confidence"],
        "probabilities": answer["probabilities"],
    }


if __name__ == "__main__":
    result = classify_component(
        state=state,
        questions=questions,
    )

    print("\nPrediction")
    print("-" * 50)

    print(f"Component type: {result['choice']}")
    print(f"Confidence:     {result['confidence']:.4f}")

    print("\nProbabilities")
    print("-" * 50)

    for label, probability in sorted(
        result["probabilities"].items(),
        key=lambda item: item[1],
        reverse=True,
    ):
        print(f"{label:25} {probability:.4f}")

    print("\nRaw result")
    print("-" * 50)

    pprint(result)