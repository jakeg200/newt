"""The mentor's orientation questionnaire. Generic questions plus one per decision option of
each of the team's task types, so it adapts to any team without code changes."""

import re
from typing import Any

GENERAL_QUESTIONS: list[tuple[str, str]] = [
    ("purpose", "In a sentence or two, what is this team responsible for?"),
    ("first_check", "When a new item arrives, what do you always check first?"),
    ("always_escalate", "What do you always escalate, whatever else is true? Who to?"),
    ("never_alone", "What should a new starter never do without asking you first?"),
    ("systems", "Which systems do you use for this work, and what would a new starter need to read, draft or change in each?"),
    ("common_mistakes", "What mistakes do new starters usually make?"),
]


def _slug(text: str, limit: int) -> str:
    return re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")[:limit] or "x"


def questions_for(task_types: list[dict[str, Any]]) -> list[dict[str, str]]:
    questions = [{"key": key, "question": q, "group": "General"} for key, q in GENERAL_QUESTIONS]
    for task in task_types:
        slug = _slug(task["name"], 40)
        for option in task["decision"]:
            questions.append(
                {
                    "key": f"{slug}.{_slug(option, 40)}",
                    "question": f"When do you choose \"{option.replace('_', ' ')}\"?",
                    "group": task["name"],
                }
            )
        for item in task.get("question_bank") or []:  # role-specific questions Newt asks during its first weeks
            questions.append({"key": f"{slug}.bank.{item['key']}", "question": item["question"], "group": task["name"]})
    return questions


def label_for(key: str) -> str:
    return f"Q.{key}"
