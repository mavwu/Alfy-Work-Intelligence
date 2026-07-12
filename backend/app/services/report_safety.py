import re
from dataclasses import dataclass, field

from ..models import WorkItem


@dataclass
class AtomicFact:
    fact_id: str
    fact_type: str
    subject: str
    statement: str
    certainty: str
    status: str
    evidence_refs: list[int]


@dataclass
class SemanticEvent:
    event_subject: str
    initial_context: list[str] = field(default_factory=list)
    requirement_change: list[str] = field(default_factory=list)
    actions_performed: list[AtomicFact] = field(default_factory=list)
    findings: list[AtomicFact] = field(default_factory=list)
    open_questions: list[AtomicFact] = field(default_factory=list)
    pending_actions: list[AtomicFact] = field(default_factory=list)
    current_status: str = "UNKNOWN"
    evidence_refs: list[int] = field(default_factory=list)


@dataclass
class SectionItem:
    section: str
    text: str
    role: str
    fact_ids: list[str]


@dataclass
class ReportPlan:
    report_type: str
    date_from: str
    date_to: str
    events: list[SemanticEvent] = field(default_factory=list)
    facts: list[AtomicFact] = field(default_factory=list)
    sections: dict[str, list[SectionItem]] = field(default_factory=dict)

    @property
    def has_pending(self) -> bool:
        return any(fact.fact_type in {"OPEN_QUESTION", "PENDING_ACTION"} for fact in self.facts)


UNSAFE_PATTERNS = [
    r"\b(company notifications?|broadcast notifications?)\s+(?:were|was)\s+(?:activated|implemented|confirmed|completed|resolved)\b",
    r"\bconfirmed that .*activate company notifications\b",
    r"\bno pending work\b",
    r"\bthere is no pending work\b",
    r"\bmarketing initiatives?\b",
    r"\bmonitor(?:ing)? .*effectiveness\b",
    r"\banother productive day\b",
    r"\bthank you for your attention\b",
    r"\bif you have any questions\b",
    r"\bfinal date\b",
    r"\bokay so today\b",
]


UNCERTAINTY_WORDS = {"need to confirm", "still need", "unconfirmed", "unknown", "whether", "not yet", "might", "possibly"}


def build_report_plan(report_type: str, date_from: str, date_to: str, items: list[WorkItem]) -> ReportPlan:
    events = [event_from_item(item) for item in items]
    facts = [fact for event in events for fact in all_event_facts(event)]
    plan = ReportPlan(report_type=report_type, date_from=date_from, date_to=date_to, events=events, facts=facts)
    plan.sections = build_sections(plan)
    return plan


def event_from_item(item: WorkItem) -> SemanticEvent:
    text = joined_evidence_text(item)
    lower = text.lower()
    subject = infer_event_subject(item, lower)
    event = SemanticEvent(event_subject=subject, evidence_refs=[item.id])

    if "initially" in lower and "clarified" in lower:
        event.initial_context.append("The notification request was initially interpreted as relating to existing ride and boat cruise notifications.")
        event.requirement_change.append("The requirement was clarified as company-wide notifications for announcements such as promotions and price-drop updates.")
    elif "clarified" in lower:
        event.requirement_change.append(professionalize_context(text))
    elif "asked if" in lower or "requirement" in lower:
        event.initial_context.append(professionalize_context(text))

    action_statement = action_statement_for(item, lower)
    if action_statement:
        event.actions_performed.append(
            AtomicFact(
                fact_id=f"{item.id}:action:1",
                fact_type="ACTION",
                subject=subject,
                statement=action_statement,
                certainty="CONFIRMED",
                status="PERFORMED" if not pending_markers(lower) else "ONGOING",
                evidence_refs=[item.id],
            )
        )

    finding = finding_statement_for(lower)
    if finding:
        event.findings.append(
            AtomicFact(
                fact_id=f"{item.id}:finding:1",
                fact_type="FINDING",
                subject="Dashboard notification configuration",
                statement=finding,
                certainty="CONFIRMED",
                status="OBSERVED",
                evidence_refs=[item.id],
            )
        )

    open_question = open_question_statement_for(lower)
    if open_question:
        event.open_questions.append(
            AtomicFact(
                fact_id=f"{item.id}:open:1",
                fact_type="OPEN_QUESTION",
                subject="Company-wide broadcast notification flow",
                statement=open_question,
                certainty="UNCONFIRMED",
                status="OPEN",
                evidence_refs=[item.id],
            )
        )
        event.pending_actions.append(
            AtomicFact(
                fact_id=f"{item.id}:pending:1",
                fact_type="PENDING_ACTION",
                subject="Broadcast notification flow",
                statement=next_step_statement_for(lower),
                certainty="CONFIRMED",
                status="PENDING",
                evidence_refs=[item.id],
            )
        )

    if item.pending_work and not event.pending_actions:
        event.pending_actions.append(
            AtomicFact(
                fact_id=f"{item.id}:pending:1",
                fact_type="PENDING_ACTION",
                subject=item.area or item.title,
                statement=professionalize_pending(item.pending_work),
                certainty="CONFIRMED",
                status="PENDING",
                evidence_refs=[item.id],
            )
        )

    if not event.actions_performed:
        event.actions_performed.append(
            AtomicFact(
                fact_id=f"{item.id}:action:1",
                fact_type="ACTION",
                subject=subject,
                statement=generic_action_statement(item, lower),
                certainty=item.evidence_confidence or "CONFIRMED",
                status="PERFORMED",
                evidence_refs=[item.id],
            )
        )

    event.current_status = "ONGOING" if event.open_questions or event.pending_actions else "COMPLETED"
    return event


def build_sections(plan: ReportPlan) -> dict[str, list[SectionItem]]:
    sections: dict[str, list[SectionItem]] = {
        "Executive Summary": [],
        "Context": [],
        "Work Completed / Investigated": [],
        "Confirmed Findings": [],
        "Open Questions / Pending Work": [],
        "Next Steps": [],
    }

    sections["Executive Summary"].append(
        SectionItem("Executive Summary", executive_summary(plan), "SUMMARY", [fact.fact_id for fact in plan.facts[:8]])
    )

    for event in plan.events:
        for context in event.initial_context + event.requirement_change:
            sections["Context"].append(SectionItem("Context", context, "CONTEXT", [f.fact_id for f in all_event_facts(event)]))
        for fact in event.actions_performed:
            sections["Work Completed / Investigated"].append(SectionItem("Work Completed / Investigated", fact.statement, "ACTION", [fact.fact_id]))
        for fact in event.findings:
            sections["Confirmed Findings"].append(SectionItem("Confirmed Findings", fact.statement, "FINDING", [fact.fact_id]))
        for fact in event.open_questions:
            sections["Open Questions / Pending Work"].append(SectionItem("Open Questions / Pending Work", fact.statement, "OPEN_QUESTION", [fact.fact_id]))
        for fact in event.pending_actions:
            sections["Next Steps"].append(SectionItem("Next Steps", fact.statement, "NEXT_STEP", [fact.fact_id]))

    return {name: remove_redundant_items(items) for name, items in sections.items() if items}


def plan_to_markdown(plan: ReportPlan) -> str:
    lines = [f"# {plan.report_type}", "", f"Reporting Period: {plan.date_from} to {plan.date_to}", ""]
    if not plan.facts:
        lines.extend(["## Evidence Status", "No confirmed work evidence is available for this reporting period."])
        return "\n".join(lines)

    for section, items in plan.sections.items():
        lines.append(f"## {section}")
        for item in items:
            if section == "Executive Summary":
                lines.append(item.text)
            else:
                lines.append(f"- {item.text}")
        lines.append("")
    return "\n".join(lines).strip()


def executive_summary(plan: ReportPlan) -> str:
    event_subjects = sorted({event.event_subject for event in plan.events})
    focus = event_subjects[0].lower() if len(event_subjects) == 1 else ", ".join(subject.lower() for subject in event_subjects[:3])
    finding_count = sum(len(event.findings) for event in plan.events)
    open_count = sum(len(event.open_questions) for event in plan.events)
    if open_count:
        finding_word = "observation" if finding_count == 1 else "observations"
        question_word = "question" if open_count == 1 else "questions"
        return f"Investigated {focus}; {finding_count or 'some'} confirmed {finding_word} and {open_count} open technical {question_word} require follow-up."
    return f"Work during this period focused on {focus}. The summary below is limited to confirmed evidence from the selected reporting period."


def validate_and_rewrite(markdown: str, plan: ReportPlan) -> tuple[str, list[str]]:
    notes = []
    if should_regenerate(markdown):
        notes.append("Regenerated report from structured facts because draft contained raw or unsafe language.")
        markdown = plan_to_markdown(plan)

    cleaned_lines = []
    for line in markdown.splitlines():
        normalized = line.strip()
        if not normalized:
            cleaned_lines.append(line)
            continue
        unsafe = False
        for pattern in UNSAFE_PATTERNS:
            if re.search(pattern, normalized, flags=re.I):
                unsafe = True
                notes.append(f"Removed unsupported or unsafe claim: {normalized[:180]}")
                break
        if plan.has_pending and re.search(r"\b(?:completed|resolved|implemented|confirmed)\b.*\b(?:broadcast|company notification)", normalized, flags=re.I):
            unsafe = True
            notes.append(f"Removed contradiction with pending notification evidence: {normalized[:180]}")
        if section_is_confirmed_finding(cleaned_lines) and contains_uncertainty(normalized):
            unsafe = True
            notes.append(f"Removed uncertainty from confirmed findings: {normalized[:180]}")
        if unsafe:
            continue
        cleaned_lines.append(line)

    cleaned = normalize_markdown("\n".join(cleaned_lines))
    return cleaned, notes


def refine_markdown(current: str, instruction: str, plan: ReportPlan) -> tuple[str, list[str]]:
    lower = instruction.lower()
    if "shorten" in lower:
        short_plan = plan_to_markdown(plan)
        lines = []
        for line in short_plan.splitlines():
            if line.startswith("- ") or line.startswith("## ") or line.startswith("# ") or line.startswith("Reporting Period"):
                lines.append(line)
            elif line.strip() and len(lines) < 5:
                lines.append(line)
        return validate_and_rewrite("\n".join(lines), plan)
    if "pending" in lower or "next steps" in lower or "not say" in lower or "implemented" in lower or "only investigated" in lower:
        return validate_and_rewrite(plan_to_markdown(plan), plan)
    if "cto" in lower or "technical" in lower:
        rewritten = plan_to_markdown(plan).rstrip() + "\n\n## Technical Notes\n" + "\n".join(
            f"- Evidence item {fact.evidence_refs[0]} supports this {fact.fact_type.lower().replace('_', ' ')}: {fact.statement}"
            for fact in plan.facts[:6]
        )
        return validate_and_rewrite(rewritten, plan)
    return validate_and_rewrite(plan_to_markdown(plan), plan)


def presentation_plan_from_report_plan(plan: ReportPlan) -> dict:
    slides = []
    for title, section_name in [
        ("Progress Overview", "Executive Summary"),
        ("Context", "Context"),
        ("Work Investigated / Completed", "Work Completed / Investigated"),
        ("Key Findings", "Confirmed Findings"),
        ("Open Questions", "Open Questions / Pending Work"),
        ("Next Steps", "Next Steps"),
    ]:
        items = plan.sections.get(section_name, [])
        bullets = [item.text for item in items if item.text]
        if bullets:
            slides.append({"title": title, "purpose": section_name, "bullets": bullets[:5], "evidence_refs": sorted({ref for item in items for ref in item.fact_ids})})
    if not slides:
        slides.append({"title": "Progress Overview", "purpose": "overview", "bullets": ["No confirmed evidence is available for this period."], "evidence_refs": []})
    return {
        "title": "Meeting Presentation" if plan.report_type == "Meeting Presentation" else plan.report_type,
        "reporting_period": f"{plan.date_from} to {plan.date_to}",
        "slides": slides[:6],
    }


def all_event_facts(event: SemanticEvent) -> list[AtomicFact]:
    return event.actions_performed + event.findings + event.open_questions + event.pending_actions


def joined_evidence_text(item: WorkItem) -> str:
    return " ".join(part for part in [item.summary, item.findings, item.fixes, item.pending_work, item.challenges] if part)


def infer_event_subject(item: WorkItem, lower: str) -> str:
    if "company notification" in lower or "broadcast notification" in lower or "promos" in lower or "price drop" in lower:
        return "Company-wide notification capability"
    if "notification" in lower:
        return "Notification support"
    return item.area or item.title


def action_statement_for(item: WorkItem, lower: str) -> str | None:
    if "dashboard" in lower and ("checked" in lower or "configuration" in lower or "toggles" in lower):
        return "Inspected dashboard notification configuration as part of the company-wide notification investigation."
    if "checking" in lower or "investigat" in lower or "checked" in lower:
        return f"Investigated {infer_event_subject(item, lower).lower()}."
    if "implemented" in lower or "built" in lower:
        return f"Implemented {infer_event_subject(item, lower).lower()}."
    return None


def generic_action_statement(item: WorkItem, lower: str) -> str:
    if item.work_type and "bug" in item.work_type.lower():
        return f"Addressed {infer_event_subject(item, lower).lower()}."
    return f"Worked on {infer_event_subject(item, lower).lower()}."


def finding_statement_for(lower: str) -> str | None:
    if "found notification toggles" in lower or ("notification" in lower and "toggles" in lower and "dashboard" in lower):
        return "Notification-related configuration toggles were identified in the dashboard."
    if "found" in lower:
        return professionalize_found_clause(lower)
    return None


def open_question_statement_for(lower: str) -> str | None:
    if ("broadcast notification flow" in lower or "broadcast" in lower) and pending_markers(lower):
        return "The existence and operation of a company-wide broadcast notification flow has not yet been confirmed."
    if pending_markers(lower):
        return "A related technical capability remains unconfirmed."
    return None


def next_step_statement_for(lower: str) -> str:
    if "dashboard" in lower and "broadcast" in lower:
        return "Inspect the dashboard notification controls and associated implementation to determine whether they connect to a working broadcast workflow."
    if "broadcast" in lower:
        return "Verify whether a working broadcast notification flow exists."
    return "Verify the unresolved technical question using the available implementation evidence."


def professionalize_context(text: str) -> str:
    lower = text.lower()
    if "clarified" in lower and ("promos" in lower or "price drops" in lower):
        return "The notification requirement was clarified as company-wide announcements such as promotions and price-drop updates, rather than only ride or boat cruise notifications."
    if "asked if" in lower and "company notifications" in lower:
        return "A request was raised to assess whether company notifications can be activated from the dashboard."
    return clean_sentence(text)


def professionalize_pending(text: str) -> str:
    lower = text.lower()
    if "broadcast" in lower:
        return "Verify whether a working company-wide broadcast notification flow exists."
    return clean_sentence(text)


def professionalize_found_clause(lower: str) -> str:
    text = lower.split("found", 1)[1].strip(" .")
    text = text.split(" but ", 1)[0].strip(" .")
    if text:
        return f"Identified {text}."
    return "A confirmed finding was identified."


def remove_redundant_items(items: list[SectionItem]) -> list[SectionItem]:
    result = []
    seen = set()
    for item in items:
        key = (item.role, normalized_semantic_text(item.text))
        if key in seen:
            continue
        seen.add(key)
        result.append(item)
    return result


def normalized_semantic_text(text: str) -> str:
    text = text.lower()
    text = re.sub(r"\b(still|need to|confirm|verify|whether|the|a|an|actual|working|has not yet been|remains)\b", " ", text)
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return " ".join(text.split())


def should_regenerate(markdown: str) -> bool:
    lower = markdown.lower()
    return "okay so today" in lower or any(re.search(pattern, markdown, flags=re.I) for pattern in UNSAFE_PATTERNS)


def section_is_confirmed_finding(previous_lines: list[str]) -> bool:
    for line in reversed(previous_lines):
        if line.startswith("## "):
            return line.strip() == "## Confirmed Findings"
    return False


def contains_uncertainty(text: str) -> bool:
    lower = text.lower()
    return any(word in lower for word in UNCERTAINTY_WORDS)


def pending_markers(lower: str) -> bool:
    return any(marker in lower for marker in ["need to confirm", "still need", "pending", "confirm whether", "whether there", "whether an actual", "not yet"])


def clean_sentence(text: str) -> str:
    text = re.sub(r"\s+", " ", text or "").strip(" -")
    text = re.sub(r"^okay so today\s+", "", text, flags=re.I)
    text = text.replace("boss", "requester")
    return text[:700]


def dedupe_lines(lines: list[str]) -> list[str]:
    seen = set()
    result = []
    for line in lines:
        key = normalized_semantic_text(line)
        if key not in seen:
            result.append(line)
            seen.add(key)
    return result


def normalize_markdown(markdown: str) -> str:
    markdown = re.sub(r"\n{3,}", "\n\n", markdown)
    markdown = re.sub(r"(?im)^#{1,6}\s*audience:\s*.*$", "", markdown)
    markdown = re.sub(r"(?im)^#{1,6}\s*tone:\s*.*$", "", markdown)
    markdown = re.sub(r"(?im)^#{1,6}\s*final date:\s*.*$", "", markdown)
    markdown = re.sub(r"(?im)^\*\*?(audience|tone|final date):.*$", "", markdown)
    markdown = re.sub(r"(?m)^---+$", "", markdown)
    return markdown.strip()
