"""JSON schema for the draft comment. Output that fails this is never posted."""
CATEGORIES = ["High Quality", "Needs Clarification", "Requires Manual Review"]

OUTPUT_SCHEMA = {
    "type": "object",
    "required": ["work_item_id", "category", "missing_information",
                 "clarification_questions", "suggested_acceptance_criteria",
                 "draft_test_cases", "draft"],
    "additionalProperties": False,
    "properties": {
        "work_item_id": {"type": "integer"},
        "category": {"enum": CATEGORIES},
        "missing_information": {"type": "array", "items": {"type": "string"}},
        "clarification_questions": {"type": "array", "items": {"type": "string"}},
        "suggested_acceptance_criteria": {"type": "array", "items": {"type": "string"}},
        "draft_test_cases": {"type": "array", "maxItems": 0},  # empty until AC approved
        "draft": {"const": True},
        "manual_review_reasons": {"type": "array", "items": {"type": "string"}},
    },
}


TESTGEN_SCHEMA = {
    "type": "object",
    "required": ["work_item_id", "draft_test_cases", "draft"],
    "additionalProperties": False,
    "properties": {
        "work_item_id": {"type": "integer"},
        "draft": {"const": True},
        "draft_test_cases": {
            "type": "array", "minItems": 1,
            "items": {
                "type": "object",
                "required": ["title", "covers_criterion", "steps", "expected_result"],
                "additionalProperties": False,
                "properties": {
                    "title": {"type": "string"},
                    "covers_criterion": {"type": "string"},
                    "steps": {"type": "array", "items": {"type": "string"}, "minItems": 1},
                    "expected_result": {"type": "string"},
                },
            },
        },
    },
}
