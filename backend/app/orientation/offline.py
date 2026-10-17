"""Offline handbook drafter used when no API key is set. It pulls rule-like sentences out of the
sources with simple patterns. Every item still cites its passage, so the whole orientation flow
(drafting, citations, editing, approval) works end to end before a model is connected."""

import html
import re
from typing import Any

from app.llm.provider import Responder

_SOURCE = re.compile(r'<source label="(?P<label>[^"]+)" document="(?P<doc>[^"]*)"[^>]*>\n(?P<text>.*?)\n</source>', re.S)
_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+|\n+")
_ESCALATE = re.compile(r"\b(escalat\w*|refer(red)? to|hand(ed)? back|sign[- ]off|approv\w+ by)\b", re.I)
_RULE = re.compile(r"\b(must|always|never|should|do not|don't|only|unless|required?|within \d+|over|above|below|under)\b", re.I)
_DEFINITION = re.compile(r"^[\"“]?(?P<term>[A-Z][\w /&-]{1,40}?)[\"”]?\s+(means|is defined as|refers to)\s+(?P<definition>.+)$")
_CONTACT = re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+|\b(contact|speak to|email|call)\b", re.I)
_ACCESS = re.compile(r"\b(?:access to|log ?in to|update|record (?:it )?in|enter (?:it )?in(?:to)?)\s+(?:the\s+)?(?P<system>[A-Z][\w-]*(?:\s[A-Z][\w-]*){0,3})")
_STEP = re.compile(r"^\s*(?:\d+[.)]|step \d+[:.]?|[-•*])\s+(?P<step>.+)$", re.I)


def _sources(user: str) -> list[dict[str, str]]:
    return [
        {"label": m["label"], "document": html.unescape(m["doc"]), "text": html.unescape(m["text"])}
        for m in _SOURCE.finditer(user)
    ]


def _sentences(text: str) -> list[str]:
    return [s.strip() for s in _SENTENCE_SPLIT.split(text) if len(s.strip()) > 12]


def draft_handbook_offline(_task: str, _system: str, user: str, _schema: dict[str, Any]) -> dict[str, Any]:
    sources = _sources(user)
    out: dict[str, Any] = {
        "purpose": {"text": "", "sources": []},
        "procedures": [],
        "decision_rules": [],
        "always_escalate": [],
        "glossary": [],
        "access_scopes": [],
        "escalation_contacts": [],
        "open_questions": ["Drafted offline from keyword patterns. Add ANTHROPIC_API_KEY for a model-written handbook."],
    }
    seen: set[str] = set()
    systems: set[str] = set()

    purpose = next((s for s in sources if s["label"] == "Q.purpose"), None)
    if purpose:
        answer = purpose["text"].split("A:", 1)[-1].strip()
        out["purpose"] = {"text": answer, "sources": [purpose["label"]]}
    elif sources:
        first = _sentences(sources[0]["text"])
        out["purpose"] = {"text": first[0] if first else sources[0]["text"][:200], "sources": [sources[0]["label"]]}

    for src in sources:
        label = src["label"]
        lines = src["text"].split("\n")
        steps = [m["step"].strip() for m in (_STEP.match(line) for line in lines) if m]
        if len(steps) >= 3:
            title = next((line.strip() for line in lines if line.strip() and not _STEP.match(line)), src["document"])
            out["procedures"].append({"title": title[:120], "steps": steps[:15], "sources": [label]})

        for sentence in _sentences(src["text"].split("A:", 1)[-1] if label.startswith("Q.") else src["text"]):
            key = sentence.lower()
            if key in seen:
                continue
            if m := _DEFINITION.match(sentence):
                out["glossary"].append({"term": m["term"], "definition": m["definition"].rstrip("."), "sources": [label]})
            elif _CONTACT.search(sentence) and _ESCALATE.search(sentence):
                out["escalation_contacts"].append({"contact": sentence, "when": "See the rule this came from", "sources": [label]})
                out["always_escalate"].append({"text": sentence, "sources": [label]})
            elif _ESCALATE.search(sentence):
                out["always_escalate"].append({"text": sentence, "sources": [label]})
            elif _RULE.search(sentence):
                out["decision_rules"].append({"text": sentence, "applies_to": "all", "sources": [label]})
            else:
                continue
            seen.add(key)
            for m in _ACCESS.finditer(sentence):
                system = m["system"].strip()
                if system.lower() not in systems:
                    systems.add(system.lower())
                    out["access_scopes"].append(
                        {"system": system, "access": "read", "reason": "Mentioned in the sources; mentor to confirm the level", "sources": [label]}
                    )

    if not out["escalation_contacts"]:
        out["open_questions"].append("Who should the agent hand cases back to, and how?")
    if not out["access_scopes"]:
        out["open_questions"].append("Which systems does the agent need, and with what access?")
    return out


def offline_responders() -> dict[str, Responder]:
    return {"handbook": draft_handbook_offline}
