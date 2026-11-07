"""Reference-based evaluation, with no model grader or paid requests.

Page relevance must be manually labelled for each question. Answer accuracy is
expected-claim coverage, not a proof of semantic correctness or financial advice.
"""

def evidence_metrics(retrieved_pages, relevant_pages):
    retrieved, relevant = set(retrieved_pages), set(relevant_pages)
    hits = len(retrieved & relevant)
    return {
        "precision": hits / len(retrieved) if retrieved else float(not relevant),
        "recall": hits / len(relevant) if relevant else float(not retrieved),
    }


def answer_accuracy(answer, expected_claims):
    if not expected_claims:
        raise ValueError("At least one verified answer claim is required")
    return sum(claim.casefold() in answer.casefold() for claim in expected_claims) / len(expected_claims)
