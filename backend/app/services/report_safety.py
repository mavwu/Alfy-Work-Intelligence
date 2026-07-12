import re
from dataclasses import dataclass, field

from ..models import WorkItem


@dataclass
class ReportFact:
    subject: str
    action: str
    status: str
    certainty: str
    evidence_refs: list[int]
    finding: str | None = None
    pending: str | None = None
    context: str | None = None


@dataclass
class ReportPlan:
    report_type: str
    date_from: str
    date_to: str
    facts: list[ReportFact] = field(default_factory=list)

    @property
    def has_pending(self) -> bool:
        return any(fact.pending or fact.status in {"ONGOING", "PENDING"} for fact in self.facts)


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
]


def build_report_plan(report_type: str, date_from: str, date_to: str, items: list[WorkItem]) -> ReportPlan:
    return ReportPlan(report_type=report_type, date_from=date_from, date_to=date_to, facts=[fact_from_item(item) for item in items])


def fact_from_item(item: WorkItem) -> ReportFact:
    text = " ".join(
        part
        for part in [item.summary, item.findings, item.fixes, item.pending_work, item.challenges]
        if part
    )
    lower = text.lower()
    status = "COMPLETED"
    action = "completed"
    certainty = item.evidence_confidence or "CONFIRMED"
    pending = item.pending_work
    finding = item.findings
    context = None

    if any(phrase in lower for phrase in ["checking", "investigat", "looked into", "reviewed", "checked"]):
        status = "ONGOING" if pending_markers(lower) else "INVESTIGATED"
        action = "investigated"
    if any(phrase in lower for phrase in ["found", "identified", "noticed"]):
        finding = finding or concise_sentence(text, ["found", "identified", "noticed"])
    if any(phrase in lower for phrase in ["clarified", "asked if", "requirement"]):
        context = concise_sentence(text, ["clarified", "asked if", "requirement"])
    if pending_markers(lower):
        status = "ONGOING"
        pending = pending or concise_sentence(text, ["need to confirm", "still need", "pending", "whether", "confirm whether"])
    if any(phrase in lower for phrase in ["i think", "maybe", "possibly", "whether"]):
        certainty = "UNVERIFIED" if certainty != "CONFIRMED" else "CONFIRMED_WITH_UNVERIFIED_DETAIL"
    if item.work_type and "bug" in item.work_type.lower() and not pending_markers(lower):
        action = "fixed"
        status = "COMPLETED"

    return ReportFact(
        subject=item.area or item.title,
        action=action,
        status=status,
        certainty=certainty,
        evidence_refs=[item.id],
        finding=finding,
        pending=pending,
        context=context,
    )


def plan_to_markdown(plan: ReportPlan) -> str:
    lines = [f"# {plan.report_type}", "", f"Reporting Period: {plan.date_from} to {plan.date_to}", ""]
    if not plan.facts:
        lines.extend(["## Evidence Status", "No confirmed work evidence is available for this reporting period."])
        return "\n".join(lines)

    lines.extend(["## Executive Summary", executive_summary(plan), ""])
    work_lines = []
    finding_lines = []
    pending_lines = []
    context_lines = []
    for fact in plan.facts:
        work_lines.append(f"- {fact.action.capitalize()} {fact.subject.lower()} ({fact.status.lower()}).")
        if fact.context:
            context_lines.append(f"- {clean_sentence(fact.context)}")
        if fact.finding:
            finding_lines.append(f"- {clean_sentence(fact.finding)}")
        if fact.pending:
            pending_lines.append(f"- {pending_sentence(fact.pending)}")

    if context_lines:
        lines.extend(["## Context", *dedupe_lines(context_lines), ""])
    lines.extend(["## Work Completed / Investigated", *dedupe_lines(work_lines), ""])
    if finding_lines:
        lines.extend(["## Confirmed Findings", *dedupe_lines(finding_lines), ""])
    if pending_lines:
        lines.extend(["## Pending Work", *dedupe_lines(pending_lines), ""])
    lines.extend(["## Next Steps", *next_steps(plan), ""])
    return "\n".join(lines).strip()


def executive_summary(plan: ReportPlan) -> str:
    subjects = sorted({fact.subject for fact in plan.facts})
    if len(subjects) == 1:
        focus = subjects[0].lower()
    else:
        focus = ", ".join(subject.lower() for subject in subjects[:3])
    if plan.has_pending:
        return f"Work during this period focused on {focus}. The evidence shows investigation and confirmed findings, with follow-up verification still required for open items."
    return f"Work during this period focused on {focus}. The summary below is limited to confirmed evidence from the selected reporting period."


def next_steps(plan: ReportPlan) -> list[str]:
    pending = [fact.pending for fact in plan.facts if fact.pending]
    if pending:
        return dedupe_lines([f"- {pending_sentence(item)}" for item in pending[:5]])
    return ["- Continue documenting confirmed work evidence as implementation progresses."]


def validate_and_rewrite(markdown: str, plan: ReportPlan) -> tuple[str, list[str]]:
    notes = []
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
        if unsafe:
            continue
        cleaned_lines.append(line)

    cleaned = "\n".join(cleaned_lines)
    if plan.has_pending and "## Pending Work" not in cleaned:
        cleaned = cleaned.rstrip() + "\n\n## Pending Work\n" + "\n".join(next_steps(plan))
        notes.append("Added pending work section from structured evidence.")
    return normalize_markdown(cleaned), notes


def refine_markdown(current: str, instruction: str, plan: ReportPlan) -> tuple[str, list[str]]:
    lower = instruction.lower()
    if "shorten" in lower:
        sections = current.split("\n## ")
        shortened = [sections[0]]
        for section in sections[1:]:
            lines = section.splitlines()
            shortened.append("\n## " + "\n".join(lines[:4]))
        return validate_and_rewrite("\n".join(shortened), plan)
    if "pending" in lower or "next steps" in lower:
        rewritten = plan_to_markdown(plan)
        return validate_and_rewrite(rewritten, plan)
    if "not say" in lower or "only investigated" in lower or "implemented" in lower:
        rewritten = current.replace("Implemented", "Investigated").replace("implemented", "investigated")
        rewritten = rewritten.replace("Confirmed company notification capability", "Investigated company notification capability")
        return validate_and_rewrite(rewritten, plan)
    if "cto" in lower or "technical" in lower:
        rewritten = current.rstrip() + "\n\n## Technical Notes\n" + "\n".join(
            f"- Evidence item {fact.evidence_refs[0]}: {fact.action.capitalize()} {fact.subject.lower()} with status {fact.status.lower()}."
            for fact in plan.facts[:6]
        )
        return validate_and_rewrite(rewritten, plan)
    rewritten = plan_to_markdown(plan)
    return validate_and_rewrite(rewritten, plan)


def pending_markers(lower: str) -> bool:
    return any(marker in lower for marker in ["need to confirm", "still need", "pending", "confirm whether", "whether there", "whether an actual"])


def concise_sentence(text: str, markers: list[str]) -> str | None:
    sentences = re.split(r"(?<=[.!?])\s+", text)
    for sentence in sentences:
        lower = sentence.lower()
        if any(marker in lower for marker in markers):
            return sentence.strip()
    return None


def pending_sentence(text: str) -> str:
    clean = clean_sentence(text)
    clean = re.sub(r"^.*?(still need to|need to|pending:?|confirm whether)", r"\1", clean, flags=re.I)
    if clean.lower().startswith("still need to"):
        return clean[0].upper() + clean[1:]
    if clean.lower().startswith("need to"):
        return "N" + clean[1:]
    if "whether" in clean.lower() and "confirm" not in clean.lower():
        return f"Confirm {clean}"
    return clean


def clean_sentence(text: str) -> str:
    text = re.sub(r"\s+", " ", text or "").strip(" -")
    text = text.replace("boss", "the requester")
    return text[:700]


def dedupe_lines(lines: list[str]) -> list[str]:
    seen = set()
    result = []
    for line in lines:
        key = line.lower()
        if key not in seen:
            result.append(line)
            seen.add(key)
    return result


def normalize_markdown(markdown: str) -> str:
    markdown = re.sub(r"\n{3,}", "\n\n", markdown)
    markdown = re.sub(r"(?im)^audience:\s*.*$", "", markdown)
    markdown = re.sub(r"(?im)^tone:\s*.*$", "", markdown)
    markdown = re.sub(r"(?m)^---+$", "", markdown)
    return markdown.strip()
