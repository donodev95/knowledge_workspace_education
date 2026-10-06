from pprint import pprint
from laya import Router

router = Router()

state = """
Question 1—Clustering (35 %)
a. Implement clustering algorithms in Python that reads and clusters data.
o Preprocess the data: handle missing values, encode categorical data, and normalize.
o Apply KMeans with Euclidean distance and initiate K = 3.
o Save the source code as 'Clustering.ipynb'.
o Determine the optimal number of clusters using the Elbow Method
and validate it using the Silhouette Score.
o Visualize the clusters in 2D using PCA or t-SNE.
b. Implement hierarchical clustering methods, such as agglomerative clustering,
to produce cluster outputs.
"""

questions = {
    "component_type": {
        "type": "choice",
        "instructions": (
            "Classify the semantic role of this extracted assessment text."
        ),
        "criteria": {
            "assessment_section": (
                "A parent assessment section or major question that contains "
                "multiple assessable requirements."
            ),
            "assessment_requirement": (
                "A specific piece of work, action, question, or evidence "
                "that the student must complete or demonstrate."
            ),
            "instruction": (
                "General directions about format, submission, tools, naming, "
                "or how the work should be completed rather than what is assessed."
            ),
            "assessment_criterion": (
                "A criterion used to grade, evaluate, or judge the student's work."
            ),
            "other": (
                "The text does not fit any of the categories above."
            ),
        },
    }
}

result = router.predict(state, questions)
pprint(result)