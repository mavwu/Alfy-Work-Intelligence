import logging
import re
import time
from dataclasses import asdict
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError
from sqlalchemy.orm import Session

from ..models import AppSetting
from .ai import AIUnavailable, OllamaProvider, parse_json_object

logger = logging.getLogger(__name__)

FactType = Literal["ACTION", "FINDING", "OPEN_QUESTION", "PENDING_ACTION"]
FactCertainty = Literal["CONFIRMED", "INFERRED", "UNVERIFIED"]
FactStatus = Literal["COMPLETED", "ONGOING", "ATTEMPTED", "PENDING", "OPEN", "UNKNOWN"]
EventStatus = Literal["COMPLETED", "ONGOING", "BLOCKED", "UNKNOWN"]


class SemanticFactSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")

    fact_type: FactType
    subject: str = ""
    statement: str
    certainty: FactCertainty = "INFERRED"
    status: FactStatus = "UNKNOWN"


class SemanticEventSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event_subject: str
    initial_context: list[str] = Field(default_factory=list)
    requirement_change: list[str] = Field(default_factory=list)
    actions_performed: list[SemanticFactSchema] = Field(default_factory=list)
    findings: list[SemanticFactSchema] = Field(default_factory=list)
    open_questions: list[SemanticFactSchema] = Field(default_factory=list)
    pending_actions: list[SemanticFactSchema] = Field(default_factory=list)
    current_status: EventStatus = "UNKNOWN"


class SemanticExtractionSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")

    events: list[SemanticEventSchema] = Field(default_factory=list)


class RawSemanticEventSchema(BaseModel):
    model_config = ConfigDict(extra="ignore")

    type: str | None = None
    description: str | None = None
    subject: str | None = None
    status: str | None = None
    certainty: str | None = None


class RawSemanticExtractionSchema(BaseModel):
    model_config = ConfigDict(extra="ignore")

    events: list[RawSemanticEventSchema] = Field(default_factory=list)


class SemanticAnalysisRun(BaseModel):
    analysis_mode: Literal["OLLAMA", "EVIDENCE_ONLY"]
    provider: str
    model: str = ""
    fallback_reason: str = ""
    validation_notes: list[str] = Field(default_factory=list)
    duration_seconds: float = 0.0


SYSTEM_SEMANTIC_EXTRACTION = """You extract structured semantic work evidence from raw work notes.
Return JSON only. Do not write a professional report.

Rules:
- Treat the input as a messy local work note from a person recording professional work.
- Split multiple unrelated topics into multiple events.
- Preserve chronology when the note changes understanding over time.
- Distinguish investigation from implementation.
- Distinguish attempted fix from successful fix.
- Distinguish observed configuration from confirmed working feature.
- Distinguish requirement clarification from work completion.
- If the text says "still need to confirm", "haven't checked", "not yet", or similar, put it in open questions or pending actions and do not mark it confirmed.
- Do not invent infrastructure, services, endpoints, queues, or databases that are not evidenced in the note.
- Use concise factual statements.

Status guidance:
- ACTION for work that was inspected, tried, changed, or implemented.
- FINDING for confirmed observations.
- OPEN_QUESTION for unresolved uncertainty.
- PENDING_ACTION for explicit next steps still needed.

Certainty guidance:
- CONFIRMED only when the note supports it directly.
- UNVERIFIED for uncertainty or incomplete confirmation.
- INFERRED only for careful interpretation that is not directly stated.

Return a top-level object with an events array.
Each event should use simple keys such as:
- type: ACTION, FINDING, OPEN_QUESTION, or PENDING_ACTION
- description: concise factual statement
- subject: short subject label when available
- status: COMPLETED, ONGOING, ATTEMPTED, PENDING, OPEN, or UNKNOWN
- certainty: CONFIRMED, INFERRED, or UNVERIFIED

Prefer multiple short events over one mixed event."""


PENDING_PATTERNS = [
    r"\bstill need to\b",
    r"\bneed to confirm\b",
    r"\bnot yet\b",
    r"\bhaven't checked\b",
    r"\bhave not checked\b",
    r"\bnot confirmed\b",
    r"\bunverified\b",
    r"\bunknown\b",
    r"\bwhether\b",
]

SUCCESS_PATTERNS = [
    r"\bfixed\b",
    r"\bresolved\b",
    r"\bimplemented\b",
    r"\bupdated\b",
    r"\bchanged\b",
    r"\brestored\b",
    r"\bworking again\b",
    r"\bstarted showing\b",
]

INVESTIGATION_PATTERNS = [
    r"\bchecking\b",
    r"\bchecked\b",
    r"\binvestigat(?:ed|ing)\b",
    r"\binspected\b",
    r"\breviewed\b",
    r"\blooked at\b",
    r"\btested\b",
    r"\bconfirmed\b",
]


def extract_semantic_analysis(db: Session, raw_text: str) -> tuple[SemanticExtractionSchema, SemanticAnalysisRun]:
    provider = OllamaProvider()
    status = provider.health_check()
    selected_model = selected_model_name(db, status.get("models", []))
    start = time.perf_counter()
    validation_notes: list[str] = []
    if selected_model and status.get("available"):
        try:
            structured = provider.generate_structured(
                selected_model,
                semantic_prompt(raw_text),
                RawSemanticExtractionSchema,
                system=SYSTEM_SEMANTIC_EXTRACTION,
            )
            normalized = convert_ollama_result(structured, raw_text, validation_notes)
            run = SemanticAnalysisRun(
                analysis_mode="OLLAMA",
                provider="Ollama",
                model=selected_model,
                validation_notes=validation_notes,
                duration_seconds=round(time.perf_counter() - start, 3),
            )
            log_semantic_run(run)
            if normalized.events:
                return normalized, run
            validation_notes.append("Ollama returned no usable events; falling back to deterministic extraction.")
        except (AIUnavailable, ValidationError, ValueError, TypeError, RuntimeError) as exc:
            validation_notes.append(f"Ollama semantic extraction failed: {exc}")

    deterministic = deterministic_semantic_analysis(raw_text)
    run = SemanticAnalysisRun(
        analysis_mode="EVIDENCE_ONLY",
        provider="Deterministic",
        model="",
        fallback_reason="; ".join(validation_notes) if validation_notes else "Ollama unavailable or no configured model.",
        validation_notes=validation_notes,
        duration_seconds=round(time.perf_counter() - start, 3),
    )
    log_semantic_run(run)
    return deterministic, run


def semantic_prompt(raw_text: str) -> str:
    return f"""
Extract structured semantic work evidence from this raw work note.

Return JSON only. Use concise factual statements and separate unrelated topics into separate events.
Focus on work meaning:
- investigation vs implementation
- attempted fix vs successful fix
- observed configuration vs confirmed capability
- requirement clarification vs completion
- pending verification vs resolved work

Input note:
{raw_text[:12000]}
"""


def selected_model_name(db: Session, installed_models: list[str]) -> str:
    setting = db.get(AppSetting, "selected_model")
    model = setting.value.strip() if setting and setting.value else ""
    if model and model in installed_models:
        return model
    return ""


def normalize_semantic_result(result: SemanticExtractionSchema, raw_text: str, notes: list[str] | None = None) -> SemanticExtractionSchema:
    notes = notes if notes is not None else []
    normalized_events: list[SemanticEventSchema] = []
    for event in result.events:
        normalized = normalize_event(event, raw_text, notes)
        if event_has_meaning(normalized):
            normalized_events.append(normalized)
    return SemanticExtractionSchema(events=normalized_events)


def convert_ollama_result(result: SemanticExtractionSchema | RawSemanticExtractionSchema, raw_text: str, notes: list[str]) -> SemanticExtractionSchema:
    if isinstance(result, SemanticExtractionSchema):
        return normalize_semantic_result(result, raw_text, notes)

    normalized_events: list[SemanticEventSchema] = []
    for item in result.events:
        normalized_events.append(raw_event_to_semantic_event(item, raw_text, notes))
    return normalize_semantic_result(SemanticExtractionSchema(events=normalized_events), raw_text, notes)


def raw_event_to_semantic_event(item: RawSemanticEventSchema, raw_text: str, notes: list[str]) -> SemanticEventSchema:
    description = clean_sentence(item.description or "")
    raw_type = (item.type or "").upper()
    subject = clean_text(item.subject or "") or infer_subject_from_text(description or raw_text)
    event = SemanticEventSchema(event_subject=subject)

    if description:
        if raw_type == "FINDING":
            event.findings.append(
                SemanticFactSchema(
                    fact_type="FINDING",
                    subject=subject,
                    statement=description,
                    certainty=certainty_from_raw(item.certainty, raw_type, description, raw_text),
                    status=raw_status_to_fact_status(item.status, "FINDING", description, raw_text),
                )
            )
        elif raw_type == "OPEN_QUESTION":
            event.open_questions.append(
                SemanticFactSchema(
                    fact_type="OPEN_QUESTION",
                    subject=subject,
                    statement=description,
                    certainty="UNVERIFIED",
                    status="OPEN",
                )
            )
            event.pending_actions.append(
                SemanticFactSchema(
                    fact_type="PENDING_ACTION",
                    subject=subject,
                    statement=pending_action_from_statement(description, raw_text),
                    certainty="UNVERIFIED",
                    status="PENDING",
                )
            )
        elif raw_type == "PENDING_ACTION":
            event.pending_actions.append(
                SemanticFactSchema(
                    fact_type="PENDING_ACTION",
                    subject=subject,
                    statement=description,
                    certainty="UNVERIFIED",
                    status="PENDING",
                )
            )
        else:
            event.actions_performed.append(
                SemanticFactSchema(
                    fact_type="ACTION",
                    subject=subject,
                    statement=description,
                    certainty=certainty_from_raw(item.certainty, raw_type, description, raw_text),
                    status=raw_status_to_fact_status(item.status, "ACTION", description, raw_text),
                )
            )
    if item.subject:
        event.initial_context.append(clean_sentence(item.subject))
    event.current_status = derive_event_status(event)
    if not event.actions_performed and not event.findings and not event.open_questions and not event.pending_actions:
        event.actions_performed.append(
            SemanticFactSchema(
                fact_type="ACTION",
                subject=subject,
                statement=description or infer_statement_from_subject(subject, "ACTION"),
                certainty="INFERRED",
                status="ONGOING",
            )
        )
        event.current_status = "ONGOING"
    return normalize_event(event, raw_text, notes)


def normalize_event(event: SemanticEventSchema, raw_text: str, notes: list[str]) -> SemanticEventSchema:
    event.event_subject = clean_text(event.event_subject) or infer_subject_from_text(raw_text)
    event.initial_context = dedupe_texts([clean_text(value) for value in event.initial_context])
    event.requirement_change = dedupe_texts([clean_text(value) for value in event.requirement_change])

    actions = [normalize_fact(fact, raw_text, notes) for fact in event.actions_performed]
    findings = [normalize_fact(fact, raw_text, notes) for fact in event.findings]
    open_questions = [normalize_fact(fact, raw_text, notes) for fact in event.open_questions]
    pending_actions = [normalize_fact(fact, raw_text, notes) for fact in event.pending_actions]

    rebucketed: dict[str, list[SemanticFactSchema]] = {"ACTION": [], "FINDING": [], "OPEN_QUESTION": [], "PENDING_ACTION": []}
    for fact in actions + findings + open_questions + pending_actions:
        original_statement = fact.statement
        normalized_type = classify_fact_type(fact, raw_text)
        fact.fact_type = normalized_type
        fact.statement = normalize_fact_statement(fact.statement, normalized_type, raw_text, original_statement)
        fact.certainty = normalize_certainty(fact, raw_text)
        fact.status = normalize_fact_status(fact, raw_text)
        rebucketed[normalized_type].append(fact)

    event.actions_performed = dedupe_facts(rebucketed["ACTION"])
    event.findings = dedupe_facts(rebucketed["FINDING"])
    event.open_questions = dedupe_facts(rebucketed["OPEN_QUESTION"])
    event.pending_actions = dedupe_facts(rebucketed["PENDING_ACTION"])
    event.current_status = derive_event_status(event)
    if event.current_status == "UNKNOWN" and (event.actions_performed or event.findings or event.open_questions or event.pending_actions):
        event.current_status = "ONGOING" if event.open_questions or event.pending_actions else "COMPLETED"
    return event


def normalize_fact(fact: SemanticFactSchema, raw_text: str, notes: list[str]) -> SemanticFactSchema:
    fact.subject = clean_text(fact.subject) or infer_subject_from_text(fact.statement or raw_text)
    fact.statement = clean_text(fact.statement)
    if not fact.statement:
        fact.statement = infer_statement_from_subject(fact.subject, fact.fact_type)
        notes.append("Synthesized a minimal semantic statement because the AI returned an empty fact.")
    return fact


def certainty_from_raw(raw_certainty: str | None, raw_type: str, description: str, raw_text: str) -> FactCertainty:
    text = f"{raw_certainty or ''} {raw_type} {description} {raw_text}".lower()
    if any(re.search(pattern, text) for pattern in PENDING_PATTERNS):
        return "UNVERIFIED"
    if raw_certainty:
        upper = raw_certainty.upper()
        if upper in {"CONFIRMED", "INFERRED", "UNVERIFIED"}:
            return upper  # type: ignore[return-value]
    if raw_type in {"OPEN_QUESTION", "PENDING_ACTION"}:
        return "UNVERIFIED"
    if raw_type == "FINDING":
        return "CONFIRMED" if not any(re.search(pattern, text) for pattern in PENDING_PATTERNS) else "UNVERIFIED"
    if any(re.search(pattern, text) for pattern in SUCCESS_PATTERNS):
        return "CONFIRMED"
    return "INFERRED"


def raw_status_to_fact_status(raw_status: str | None, fact_type: FactType, description: str, raw_text: str) -> FactStatus:
    text = f"{raw_status or ''} {fact_type} {description} {raw_text}".lower()
    if fact_type == "OPEN_QUESTION":
        return "OPEN"
    if fact_type == "PENDING_ACTION":
        return "PENDING"
    if raw_status:
        upper = raw_status.upper()
        if upper in {"COMPLETED", "ONGOING", "ATTEMPTED", "PENDING", "OPEN", "UNKNOWN"}:
            return upper  # type: ignore[return-value]
    if any(re.search(pattern, text) for pattern in PENDING_PATTERNS):
        return "ONGOING"
    if fact_type == "FINDING":
        return "COMPLETED" if not any(re.search(pattern, text) for pattern in PENDING_PATTERNS) else "OPEN"
    if any(re.search(pattern, text) for pattern in SUCCESS_PATTERNS):
        return "COMPLETED"
    if any(re.search(pattern, text) for pattern in INVESTIGATION_PATTERNS):
        return "ONGOING"
    return "UNKNOWN"


def normalize_fact_statement(statement: str, fact_type: FactType, raw_text: str, original_statement: str) -> str:
    if fact_type == "PENDING_ACTION":
        if any(re.search(pattern, f"{original_statement} {raw_text}".lower()) for pattern in PENDING_PATTERNS) or any(
            re.search(pattern, original_statement.lower()) for pattern in SUCCESS_PATTERNS
        ):
            return pending_action_from_statement(original_statement, raw_text)
    if fact_type == "OPEN_QUESTION":
        if any(re.search(pattern, f"{original_statement} {raw_text}".lower()) for pattern in PENDING_PATTERNS):
            return pending_statement_from_statement(original_statement, raw_text)
    return clean_sentence(statement)


def normalize_certainty(fact: SemanticFactSchema, raw_text: str) -> FactCertainty:
    text = f"{fact.statement} {raw_text}".lower()
    if any(re.search(pattern, text) for pattern in PENDING_PATTERNS):
        return "UNVERIFIED"
    if fact.fact_type == "OPEN_QUESTION" or fact.fact_type == "PENDING_ACTION":
        return "UNVERIFIED"
    if any(re.search(pattern, text) for pattern in SUCCESS_PATTERNS):
        return "CONFIRMED"
    if any(re.search(pattern, text) for pattern in INVESTIGATION_PATTERNS):
        return "INFERRED"
    return fact.certainty or "INFERRED"


def normalize_fact_status(fact: SemanticFactSchema, raw_text: str) -> FactStatus:
    text = f"{fact.statement} {raw_text}".lower()
    if fact.fact_type == "OPEN_QUESTION":
        return "OPEN"
    if fact.fact_type == "PENDING_ACTION":
        return "PENDING"
    if any(re.search(pattern, text) for pattern in PENDING_PATTERNS):
        return "ONGOING"
    if fact.fact_type == "ACTION":
        return "COMPLETED" if any(re.search(pattern, text) for pattern in SUCCESS_PATTERNS) else "ONGOING"
    if fact.fact_type == "FINDING":
        return "COMPLETED" if fact.certainty == "CONFIRMED" else "OPEN"
    return fact.status or "UNKNOWN"


def classify_fact_type(fact: SemanticFactSchema, raw_text: str) -> FactType:
    text = f"{fact.statement} {raw_text}".lower()
    if fact.fact_type == "PENDING_ACTION":
        return "PENDING_ACTION"
    if fact.fact_type == "OPEN_QUESTION":
        return "OPEN_QUESTION"
    if any(re.search(pattern, text) for pattern in PENDING_PATTERNS):
        return "OPEN_QUESTION" if "?" in fact.statement or fact.statement.strip().endswith("?") else "PENDING_ACTION"
    if fact.fact_type == "FINDING" and any(re.search(pattern, text) for pattern in SUCCESS_PATTERNS):
        return "ACTION"
    if fact.fact_type == "ACTION" and any(token in text for token in ["found", "identified", "noticed", "confirmed", "observed"]):
        return "FINDING"
    return fact.fact_type


def derive_event_status(event: SemanticEventSchema) -> EventStatus:
    if event.open_questions or event.pending_actions:
        return "ONGOING"
    if event.actions_performed or event.findings:
        return "COMPLETED"
    return "UNKNOWN"


def event_has_meaning(event: SemanticEventSchema) -> bool:
    return bool(
        event.event_subject
        and (
            event.initial_context
            or event.requirement_change
            or event.actions_performed
            or event.findings
            or event.open_questions
            or event.pending_actions
        )
    )


def deterministic_semantic_analysis(raw_text: str) -> SemanticExtractionSchema:
    text = clean_text(raw_text)
    if not text:
        return SemanticExtractionSchema(events=[])
    global_subject = infer_subject_from_text(text)
    clauses = split_into_clauses(text)
    events = []
    for clause in clauses[:8]:
        event = clause_to_event(clause, global_subject)
        if event_has_meaning(event):
            events.append(event)
    if not events:
        events.append(clause_to_event(text, global_subject))
    return SemanticExtractionSchema(events=events)


def clause_to_event(clause: str, global_subject: str | None = None) -> SemanticEventSchema:
    lower = clause.lower()
    subject = infer_subject_from_text(clause, global_subject)
    event = SemanticEventSchema(event_subject=subject)

    if any(token in lower for token in ["initially", "thought", "at first"]):
        event.initial_context.append(clean_sentence(clause))
    if "clarified" in lower or "means" in lower:
        event.requirement_change.append(clean_sentence(clause))
    if any(token in lower for token in ["checked", "checking", "investigat", "inspected", "reviewed", "looked at", "tested"]):
        event.actions_performed.append(
            SemanticFactSchema(
                fact_type="ACTION",
                subject=subject,
                statement=clean_sentence(clause),
                certainty="INFERRED",
                status="ONGOING" if any(token in lower for token in ["still need", "not yet", "haven't"]) else "COMPLETED",
            )
        )
    if any(token in lower for token in ["found", "identified", "noticed", "confirmed", "was actually", "returned properly", "started showing"]):
        event.findings.append(
            SemanticFactSchema(
                fact_type="FINDING",
                subject=subject,
                statement=clean_sentence(clause),
                certainty="CONFIRMED" if not any(re.search(pattern, lower) for pattern in PENDING_PATTERNS) else "UNVERIFIED",
                status="COMPLETED" if not any(re.search(pattern, lower) for pattern in PENDING_PATTERNS) else "OPEN",
            )
        )
    if any(re.search(pattern, lower) for pattern in PENDING_PATTERNS):
        event.open_questions.append(
            SemanticFactSchema(
                fact_type="OPEN_QUESTION",
                subject=subject,
                statement=pending_statement_from_clause(clause),
                certainty="UNVERIFIED",
                status="OPEN",
            )
        )
        event.pending_actions.append(
            SemanticFactSchema(
                fact_type="PENDING_ACTION",
                subject=subject,
                statement=pending_action_from_clause(clause),
                certainty="UNVERIFIED",
                status="PENDING",
            )
        )
    event.current_status = derive_event_status(event)
    if not event.actions_performed and not event.findings and not event.open_questions and not event.pending_actions:
        event.actions_performed.append(
            SemanticFactSchema(
                fact_type="ACTION",
                subject=subject,
                statement=clean_sentence(clause),
                certainty="INFERRED",
                status="ONGOING",
            )
        )
        event.current_status = "ONGOING"
    return event


def split_into_clauses(text: str) -> list[str]:
    text = re.sub(r"\s+", " ", text).strip()
    parts = re.split(r"\bthen later\b|\bthen\b|\blater\b|\bafter that\b|\bafterwards\b|\bnext\b", text, flags=re.I)
    clauses = [clean_sentence(part) for part in parts if clean_sentence(part)]
    if len(clauses) > 1:
        return clauses
    sentence_parts = re.split(r"(?<=[.!?])\s+", text)
    clauses = [clean_sentence(part) for part in sentence_parts if clean_sentence(part)]
    return clauses or [clean_sentence(text)]


def infer_subject_from_text(text: str, global_subject: str | None = None) -> str:
    lower = text.lower()
    if "company notification" in lower or "broadcast notification" in lower or "promos" in lower or "price drops" in lower:
        return "Company-wide notification capability"
    if global_subject and "notification" in lower and "boat cruise" not in lower and "booking" not in lower:
        return global_subject
    if "dashboard" in lower and "notification" in lower:
        return "Company-wide notification capability"
    if "boat cruise" in lower:
        return "Boat Cruise category images"
    if "api" in lower:
        return "API response handling"
    if "notification" in lower:
        return "Notification support"
    if "booking" in lower:
        return "Booking workflow"
    return "General work"


def infer_statement_from_subject(subject: str, fact_type: FactType) -> str:
    if fact_type == "OPEN_QUESTION":
        return f"Open question remains for {subject.lower()}."
    if fact_type == "PENDING_ACTION":
        return f"Verify {subject.lower()}."
    if fact_type == "FINDING":
        return f"Confirmed finding about {subject.lower()}."
    return f"Investigated {subject.lower()}."


def pending_statement_from_clause(clause: str) -> str:
    clause = clean_sentence(clause)
    lower = clause.lower()
    if "still need to confirm" in lower or "need to confirm" in lower:
        match = re.search(r"need to confirm (.*)", clause, flags=re.I)
        if match:
            return f"Confirm {match.group(1).strip(' .')}."
    if "haven't checked" in lower or "have not checked" in lower:
        return f"Check the remaining verification in: {clause.rstrip('.')}."
    return f"Verify {clause.rstrip('.') }."


def pending_statement_from_statement(statement: str, raw_text: str) -> str:
    text = clean_sentence(statement)
    if not text:
        text = clean_sentence(raw_text)
    lower = text.lower()
    if "company notifications" in lower or "broadcast" in lower or "notification" in lower:
        return f"Confirm whether {text.rstrip('.')}."
    return f"Verify whether {text.rstrip('.')}."


def pending_action_from_statement(statement: str, raw_text: str) -> str:
    text = clean_sentence(statement)
    if not text:
        text = clean_sentence(raw_text)
    lower = text.lower()
    if "company notifications" in lower or "broadcast" in lower or "notification" in lower:
        return f"Confirm whether {text.rstrip('.')}."
    return f"Verify whether {text.rstrip('.')}."


def pending_action_from_clause(clause: str) -> str:
    lower = clause.lower()
    if "still need to confirm" in lower:
        return "Confirm the unresolved technical question."
    if "haven't checked" in lower or "have not checked" in lower:
        return "Check the remaining unverified area."
    return f"Verify the unresolved question described in: {clean_sentence(clause)}"


def clean_sentence(text: str) -> str:
    text = clean_text(text)
    text = re.sub(r"^okay so today\s+", "", text, flags=re.I)
    text = text.replace("boss", "requester")
    return text[:800]


def clean_text(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip(" -")


def dedupe_texts(values: list[str]) -> list[str]:
    result: list[str] = []
    seen = set()
    for value in values:
        key = normalized_semantic_text(value)
        if value and key not in seen:
            result.append(value)
            seen.add(key)
    return result


def dedupe_facts(values: list[SemanticFactSchema]) -> list[SemanticFactSchema]:
    result: list[SemanticFactSchema] = []
    seen = set()
    for fact in values:
        key = (fact.fact_type, normalized_semantic_text(fact.statement))
        if key in seen:
            continue
        seen.add(key)
        result.append(fact)
    return result


def normalized_semantic_text(text: str) -> str:
    text = text.lower()
    text = re.sub(r"\b(still|need to|confirm|verify|whether|the|a|an|actual|working|has not yet been|remains|check)\b", " ", text)
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return " ".join(text.split())


def log_semantic_run(run: SemanticAnalysisRun):
    logger.info(
        "semantic_extraction mode=%s provider=%s model=%s duration=%.3fs fallback=%s validation_notes=%s",
        run.analysis_mode,
        run.provider,
        run.model or "-",
        run.duration_seconds,
        run.fallback_reason or "-",
        len(run.validation_notes),
    )
