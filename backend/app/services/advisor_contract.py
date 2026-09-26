"""Validation for the open-ended advisor.v1 model response."""

import json
import re
from typing import Any

from .prompt_guard import validate_ai_output

_FENCED_JSON = re.compile(r"^```(?:json)?\s*(.*?)\s*```$", re.IGNORECASE | re.DOTALL)
_SAFE_ACTIONS = {"review_evidence", "review_accounts", "review_budgets", "review_goals", "add_or_import"}

ADVISOR_RESPONSE_INSTRUCTION = """
Open-ended Advisor response contract: return ONLY JSON, never Markdown or prose outside JSON:
{"answer":"string", "claims":[{"text":"verifiable factual claim", "evidence_ids":["current transaction UUID"]}], "assumptions":["short string"], "uncertainties":["short string"], "suggested_actions":[{"type":"review_evidence|review_accounts|review_budgets|review_goals|add_or_import", "label":"short string", "transaction_ids":[]}]}
Every factual claim must cite one or more transaction IDs from the supplied Ledger context. Put general advice in answer without presenting it as a Ledger fact. Never invent IDs, amounts, dates, categories, merchants, or actions.
""".strip()


def parse_advisor_response(raw: str) -> dict[str, Any] | None:
    """Parse only the bounded JSON response shape; prose is not trusted as a contract."""
    text = (raw or "").strip()
    match = _FENCED_JSON.match(text)
    if match:
        text = match.group(1).strip()
    try:
        parsed = json.loads(text)
    except (TypeError, json.JSONDecodeError):
        return None
    return parsed if isinstance(parsed, dict) else None


def validate_advisor_response(
    raw: str,
    financial_context: str,
    currency: str,
    valid_evidence_ids: set[str],
    allowed_entities: set[str],
) -> dict[str, Any]:
    """Validate answer text and every factual claim against current evidence."""
    parsed = parse_advisor_response(raw)
    if not parsed or not isinstance(parsed.get("answer"), str) or not parsed["answer"].strip():
        return {"valid": False, "reason": "response is not advisor.v1 JSON"}
    answer_guard = validate_ai_output(parsed["answer"], financial_context, currency, allowed_entities)
    if not answer_guard["valid"]:
        return {"valid": False, "reason": "answer failed grounding", "guard": answer_guard}
    claims = parsed.get("claims")
    if not isinstance(claims, list) or len(claims) > 20:
        return {"valid": False, "reason": "claims must be a bounded list"}

    normalized_claims: list[dict[str, Any]] = []
    all_evidence: list[str] = []
    for claim in claims:
        if not isinstance(claim, dict) or not isinstance(claim.get("text"), str):
            return {"valid": False, "reason": "each claim needs text and evidence_ids"}
        evidence_ids = claim.get("evidence_ids")
        if not isinstance(evidence_ids, list) or not evidence_ids or not all(isinstance(item, str) for item in evidence_ids):
            return {"valid": False, "reason": "every factual claim requires evidence_ids"}
        evidence_ids = list(dict.fromkeys(evidence_ids))[:20]
        if any(item not in valid_evidence_ids for item in evidence_ids):
            return {"valid": False, "reason": "claim cites evidence outside the current user"}
        guard = validate_ai_output(claim["text"], financial_context, currency, allowed_entities)
        if not guard["valid"]:
            return {"valid": False, "reason": "claim failed grounding", "guard": guard}
        normalized_claims.append({"text": claim["text"].strip(), "evidence_ids": evidence_ids})
        all_evidence.extend(evidence_ids)

    assumptions = parsed.get("assumptions", [])
    uncertainties = parsed.get("uncertainties", [])
    if not all(isinstance(item, str) and len(item) <= 300 for item in (*assumptions, *uncertainties)):
        return {"valid": False, "reason": "assumptions and uncertainties must be short strings"}

    # Model actions are advisory descriptors only; reject unknown or mutating
    # action types rather than allowing the model to expand permissions.
    actions = parsed.get("suggested_actions", [])
    if not isinstance(actions, list) or len(actions) > 3:
        return {"valid": False, "reason": "suggested_actions must be bounded"}
    normalized_actions = []
    for action in actions:
        if not isinstance(action, dict) or action.get("type") not in _SAFE_ACTIONS:
            return {"valid": False, "reason": "unsupported advisor action"}
        action_ids = action.get("transaction_ids", [])
        if not isinstance(action_ids, list) or not all(item in valid_evidence_ids for item in action_ids):
            return {"valid": False, "reason": "action cites invalid evidence"}
        normalized_actions.append({"type": action["type"], "label": str(action.get("label") or "Review evidence")[:120], "transaction_ids": action_ids[:20]})

    unique_evidence = list(dict.fromkeys(all_evidence))
    return {
        "valid": True,
        "answer": parsed["answer"].strip()[:6000],
        "claims": normalized_claims,
        "assumptions": list(assumptions)[:10],
        "uncertainties": list(uncertainties)[:10],
        "suggested_actions": normalized_actions,
        "evidence_ids": unique_evidence[:100],
        "evidence_coverage": 1.0 if normalized_claims else 0.0,
    }
