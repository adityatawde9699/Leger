"""Amadeus advisor: deterministic answers first, then the grounded LLM reply streamed over SSE."""

import hashlib
import json
import logging

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from ..auth import get_current_user
from ..cache import _user_cache_version, llm_cache
from ..config import settings
from ..db import get_db
from ..helpers import (
    _account_currency_mismatch_count,
    _format_overspending,
    _format_transaction,
    _tx_query,
    _wants_last_transaction,
    _wants_overspending,
)
from ..models import AIConversation, AIMessage, Budget, User
from ..rate_limit import limiter
from ..schemas import AdvisorRequest, UserContext
from ..services.advisor_contract import ADVISOR_RESPONSE_INSTRUCTION, validate_advisor_response
from ..services.advisor_facts import deterministic_answer
from ..services.advisor_tools import (
    TOOL_SELECTION_SYSTEM,
    execute_tool_request,
    parse_tool_request,
    select_advisor_tools,
)
from ..services.ai_router import ai_router
from ..services.anomaly_detector import detect_anomalies
from ..services.forecaster import generate_forecast
from ..services.insights import SYSTEM_PROMPT, build_advisor_context, data_quality
from ..services.privacy import purge_expired_conversations, redact_sensitive_text, safe_conversation_memory
from ..services.prompt_guard import build_safe_messages, sanitize_user_input

router = APIRouter()
logger = logging.getLogger("ledger.api")


# ── AI Advisor (streaming) ────────────────────────────────────────────────────
@router.post("/advisor/stream")
@limiter.limit(settings.advisor_rate_limit)
async def advisor_stream(
    request: Request,
    payload: AdvisorRequest,
    user: UserContext = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    question = sanitize_user_input(payload.question)
    ai_question = redact_sensitive_text(question)
    db_user = db.get(User, user.id)
    cloud_ai_enabled = bool(db_user.cloud_ai_enabled) if db_user else False
    currency = db_user.currency_preference if db_user else "INR"
    transactions = _tx_query(db, user.id).limit(500).all()
    advisor_entities = {
        value.strip()
        for tx in transactions
        for value in (tx.category, tx.merchant_normalized or tx.description)
        if isinstance(value, str) and value.strip()
    }
    budgets = db.query(Budget).filter(Budget.user_id == user.id).all()
    tool_results = select_advisor_tools(question, transactions, budgets, currency)
    advisor_quality = data_quality(transactions)
    currency_mismatch_count = _account_currency_mismatch_count(db, user.id)
    if currency_mismatch_count:
        advisor_quality["warnings"].append(
            "Account currencies differ from your Ledger currency; combined totals are unreliable"
        )
    advisor_meta = {
        "type": "meta",
        "answer_type": "ai",
        "response_contract": "advisor.v1",
        "answer_mode": payload.answer_mode,
        "currency": currency,
        "cloud_ai_configured": bool(ai_router.configured_providers("advisor")),
        "cloud_ai_enabled": cloud_ai_enabled,
        "configured_providers": ai_router.configured_providers("advisor"),
        "provider_retention_policy": ai_router.provider_retention_policy(),
        "provider_regions": ai_router.provider_regions(),
        "calculation_source": "Ledger",
        "explanation_source": "cloud_ai",
        "privacy": {
            "cloud_ai_enabled": cloud_ai_enabled,
            "financial_history_sent": bool(cloud_ai_enabled),
            "provider_retention": ai_router.provider_retention_policy(),
        },
        "data_range": {
            "start": advisor_quality.get("period_start"),
            "end": advisor_quality.get("period_end"),
            "transaction_count": advisor_quality.get("transaction_count", len(transactions)),
        },
        "period_start": advisor_quality.get("period_start"),
        "period_end": advisor_quality.get("period_end"),
        "transaction_count": advisor_quality.get("transaction_count", len(transactions)),
        "coverage": advisor_quality.get("coverage", "none"),
        "warnings": advisor_quality.get("warnings", []),
        # Keep the transport contract stable for both deterministic and AI
        # answers. Deterministic answers populate these fields below; the AI
        # path starts conservatively and must not imply evidence it has not
        # actually returned.
        "facts": [],
        "assumptions": [],
        "uncertainties": ["This explanation is generated from the current Ledger context; verify important decisions against the evidence shown."],
        "suggested_actions": [],
        "source_links": [],
        "tool_results": tool_results,
        "grounding_status": "pending",
        "evidence_coverage": 0.0,
    }

    if currency_mismatch_count:
        advisor_meta["answer_type"] = "deterministic"
        advisor_meta["explanation_source"] = "Ledger rules"
        advisor_meta["privacy"]["financial_history_sent"] = False
        advisor_meta["uncertainties"] = [
            "Account currencies differ from the Ledger currency, so combined totals cannot be calculated reliably."
        ]
        advisor_meta["suggested_actions"] = [{
            "type": "review_accounts",
            "label": "Review account currencies",
        }]

        async def currency_warning_events():
            yield f"data: {json.dumps(advisor_meta)}\n\n"
            yield f"data: {json.dumps('I cannot give a reliable answer while account currencies differ from your Ledger currency. Review your accounts and currency setting first.')}\n\n"
            yield "data: [DONE]\n\n"

        return StreamingResponse(
            currency_warning_events(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache"},
        )

    if db_user and not db_user.cloud_ai_enabled:
        advisor_meta["answer_type"] = "unavailable"
        advisor_meta["explanation_source"] = "Ledger rules"
        advisor_meta["privacy"]["financial_history_sent"] = False
        advisor_meta["uncertainties"] = ["Cloud AI is disabled in Profile. Ledger can still answer direct factual questions without a provider."]
        advisor_meta["suggested_actions"] = [{"type": "enable_cloud_ai", "label": "Enable cloud AI in Profile"}]

        async def cloud_ai_disabled_events():
            fact_answer = deterministic_answer(question, transactions, budgets, currency)
            yield f"data: {json.dumps(advisor_meta)}\n\n"
            if fact_answer:
                yield f"data: {json.dumps(fact_answer['answer'])}\n\n"
            else:
                yield f"data: {json.dumps('Cloud AI is disabled, so I can only answer direct factual questions from your Ledger data. Enable it in Profile for explanations and planning.') }\n\n"
            yield "data: [DONE]\n\n"

        return StreamingResponse(
            cloud_ai_disabled_events(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache"},
        )

    fact_answer = deterministic_answer(question, transactions, budgets, currency)
    if fact_answer:
        advisor_meta.update({k: v for k, v in fact_answer.items() if k != "answer"})
        advisor_meta["explanation_source"] = "Ledger rules"
        advisor_meta["privacy"]["financial_history_sent"] = False

        async def deterministic_event_generator():
            yield f"data: {json.dumps(advisor_meta)}\n\n"
            yield f"data: {json.dumps(fact_answer['answer'])}\n\n"
            yield "data: [DONE]\n\n"

        return StreamingResponse(
            deterministic_event_generator(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache"},
        )

    if _wants_last_transaction(question):
        latest = transactions[0] if transactions else None
        answer = _format_transaction(latest, currency) if latest else "No transactions were found for this signed-in account."
        if latest:
            advisor_meta["explanation_source"] = "Ledger rules"
            advisor_meta["privacy"]["financial_history_sent"] = False
            advisor_meta.update({
                "answer_type": "deterministic",
                "facts": [{"label": "Latest transaction", "transaction_id": latest.id, "value": str(latest.amount)}],
                "evidence": [{
                    "transaction_id": latest.id,
                    "date": latest.date.isoformat(),
                    "description": latest.merchant_normalized or latest.description,
                    "amount": str(latest.amount),
                    "type": latest.type,
                    "category": latest.category,
                }],
                "assumptions": ["Transactions are ordered by recorded date."],
                "uncertainties": [],
                "suggested_actions": [{
                    "type": "review_evidence",
                    "label": "Open Activity",
                    "transaction_ids": [latest.id],
                }],
                "source_links": [{
                    "type": "transactions",
                    "label": "View latest transaction in Activity",
                    "transaction_ids": [latest.id],
                }],
            })

        async def last_tx_event_generator():
            yield f"data: {json.dumps(advisor_meta)}\n\n"
            yield f"data: {json.dumps(answer)}\n\n"
            yield "data: [DONE]\n\n"

        return StreamingResponse(
            last_tx_event_generator(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache"},
        )

    if _wants_overspending(question):
        answer = _format_overspending(transactions, currency)
        advisor_meta["answer_type"] = "deterministic"
        advisor_meta["explanation_source"] = "Ledger rules"
        advisor_meta["privacy"]["financial_history_sent"] = False

        async def overspending_event_generator():
            yield f"data: {json.dumps(advisor_meta)}\n\n"
            yield f"data: {json.dumps(answer)}\n\n"
            yield "data: [DONE]\n\n"

        return StreamingResponse(
            overspending_event_generator(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache"},
        )

    if not transactions:
        advisor_meta["answer_type"] = "deterministic"
        advisor_meta["explanation_source"] = "Ledger rules"
        advisor_meta["privacy"]["financial_history_sent"] = False
        advisor_meta["uncertainties"] = ["There is no transaction history to support a personalized explanation."]
        advisor_meta["suggested_actions"] = [{"type": "add_or_import", "label": "Add or import transactions"}]

        async def no_data_event_generator():
            yield f"data: {json.dumps(advisor_meta)}\n\n"
            yield f"data: {json.dumps('I do not have enough Ledger history to answer that personally yet. Add or import a few transactions, then ask again so I can show the evidence and math.') }\n\n"
            yield "data: [DONE]\n\n"

        return StreamingResponse(
            no_data_event_generator(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache"},
        )

    # Enrich advisor context with anomalies + forecast
    anomalies = detect_anomalies(transactions, currency)
    forecast = generate_forecast(transactions)
    if cloud_ai_enabled and ai_router.configured_providers("advisor_tools"):
        try:
            raw_tool_request = await ai_router.generate(
                TOOL_SELECTION_SYSTEM,
                [{"role": "user", "content": ai_question}],
                task_type="advisor_tools",
            )
            tool_request = parse_tool_request(raw_tool_request)
            selected_tool = execute_tool_request(tool_request, transactions, budgets, currency) if tool_request else None
            if selected_tool:
                tool_results = [result for result in tool_results if result.get("tool") != selected_tool.get("tool")]
                tool_results.append(selected_tool)
                advisor_meta["tool_results"] = tool_results
        except Exception as tool_error:
            logger.warning("advisor.tool_selection.failed user=%s error=%s", user.id, type(tool_error).__name__)
    context = build_advisor_context(
        transactions,
        budgets,
        anomalies=anomalies,
        forecast=forecast,
        currency=currency,
        recurring_tolerance=db_user.recurring_tolerance if db_user else "standard",
    )
    context += f"\n\n[Deterministic advisor tools — calculated by Ledger]\n{json.dumps(tool_results, sort_keys=True, default=str)}\n[/Deterministic advisor tools]"

    # Load conversation history if continuing a thread
    history = []
    conversation = None
    if payload.conversation_id:
        purge_expired_conversations(db, user.id, settings.ai_conversation_retention_days)
        conversation = (
            db.query(AIConversation)
            .filter(
                AIConversation.id == payload.conversation_id,
                AIConversation.user_id == user.id,
            )
            .first()
        )
        if conversation:
            history = safe_conversation_memory([
                {"role": m.role, "content": m.content}
                for m in sorted(conversation.messages, key=lambda m: m.created_at)
            ])

    mode_instruction = {
        "quick": "Answer mode: quick answer. Lead with the concise conclusion and one next step.",
        "math": "Answer mode: show the math. State the relevant Ledger facts, period, assumptions, and calculation before the conclusion.",
        "plan": "Answer mode: plan with me. Use only evidenced facts, state assumptions, and propose at most three reversible next steps.",
    }[payload.answer_mode]
    messages = build_safe_messages(
        f"{SYSTEM_PROMPT}\n\n{ADVISOR_RESPONSE_INSTRUCTION}",
        context,
        f"{mode_instruction}\nUser question: {ai_question}",
        history,
    )

    # Create or update conversation
    if not conversation:
        conversation = AIConversation(
            user_id=user.id,
            title=ai_question[:80],
        )
        db.add(conversation)
        db.commit()
        db.refresh(conversation)

    user_msg = AIMessage(conversation_id=conversation.id, role="user", content=ai_question)
    db.add(user_msg)
    db.commit()

    # Hash the complete message context, scoped to the user. The user prefix is
    # required so TTLCache.invalidate_user (which matches on the "{user_id}:"
    # prefix) actually evicts these entries when the user corrects a category —
    # otherwise stale advice lingers. It also rules out cross-user cache hits.
    context_hash = hashlib.sha256(json.dumps(messages).encode()).hexdigest()
    cache_key = f"{user.id}:advisor:{_user_cache_version(db, user.id)}:{context_hash}"
    cached_reply = llm_cache.get(cache_key)

    valid_evidence_ids = {tx.id for tx in transactions}
    evidence_by_id = {
        tx.id: {
            "transaction_id": tx.id,
            "date": tx.date.isoformat(),
            "description": tx.merchant_normalized or tx.description,
            "amount": str(tx.amount),
            "type": tx.type,
            "category": tx.category,
        }
        for tx in transactions
    }

    def ground_advisor_reply(raw: str) -> tuple[str, dict[str, object] | None]:
        contract = validate_advisor_response(
            raw, context, currency, valid_evidence_ids, advisor_entities,
        )
        if not contract.get("valid"):
            logger.warning("advisor.structured_output.rejected user=%s", user.id)
            advisor_meta["grounding_status"] = "rejected"
            advisor_meta["uncertainties"] = [
                "The AI response did not provide a verifiable structured claim set, so Ledger withheld it."
            ]
            advisor_meta["suggested_actions"] = [{"type": "ask_deterministic", "label": "Ask Ledger to show the math"}]
            return (
                "I couldn't verify that explanation against your current Ledger evidence. Try a direct factual question or ask me to show the math.",
                None,
            )
        advisor_meta["grounding_status"] = "validated"
        advisor_meta["facts"] = contract["claims"]
        advisor_meta["assumptions"] = contract["assumptions"]
        advisor_meta["uncertainties"] = contract["uncertainties"]
        advisor_meta["suggested_actions"] = contract["suggested_actions"]
        advisor_meta["evidence_coverage"] = contract["evidence_coverage"]
        advisor_meta["evidence"] = [evidence_by_id[item] for item in contract["evidence_ids"] if item in evidence_by_id]
        advisor_meta["source_links"] = ([{
            "type": "transactions",
            "label": "Review supporting transactions",
            "transaction_ids": contract["evidence_ids"],
        }] if contract["evidence_ids"] else [])
        return contract["answer"], contract

    if cached_reply:
        logger.info("Cache hit for advisor stream.")

        async def cached_event_generator():
            reply, _contract = ground_advisor_reply(cached_reply)
            yield f"data: {json.dumps(advisor_meta)}\n\n"
            # Yield cached string fully — JSON-encoded so embedded newlines
            # (markdown bullet points, paragraphs) survive SSE line parsing.
            yield f"data: {json.dumps(reply)}\n\n"

            assistant_msg = AIMessage(
                conversation_id=conversation.id,
                role="assistant",
                content=reply,
            )
            db.add(assistant_msg)
            db.commit()
            yield "data: [DONE]\n\n"

        return StreamingResponse(
            cached_event_generator(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "X-Conversation-Id": conversation.id,
            },
        )

    async def event_generator():
        full_reply = []
        try:
            async for token in ai_router.stream(
                f"{SYSTEM_PROMPT}\n\n{ADVISOR_RESPONSE_INSTRUCTION}", messages, task_type="advisor"
            ):
                full_reply.append(token)
            raw_reply = "".join(full_reply)
            reply_text, _contract = ground_advisor_reply(raw_reply)
            yield f"data: {json.dumps(advisor_meta)}\n\n"
            yield f"data: {json.dumps(reply_text)}\n\n"
        except Exception:
            logger.exception("advisor.stream.error user=%s", user.id)
            yield "data: [ERROR] The advisor could not answer right now. Please try again.\n\n"
        finally:
            # Persist assistant reply
            if full_reply:
                raw_reply = "".join(full_reply)
                reply_text, contract = ground_advisor_reply(raw_reply)
                llm_cache.put(cache_key, raw_reply if contract else reply_text)

                assistant_msg = AIMessage(
                    conversation_id=conversation.id,
                    role="assistant",
                    content=reply_text,
                )
                db.add(assistant_msg)
                db.commit()
            yield "data: [DONE]\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Conversation-Id": conversation.id,
        },
    )


@router.get("/ai/provider-health")
def ai_provider_health(
    user: UserContext = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Expose credential-free provider health for diagnostics and settings UI."""
    db_user = db.get(User, user.id)
    return {
        "cloud_ai_enabled": bool(db_user.cloud_ai_enabled) if db_user else False,
        "providers": ai_router.provider_health("advisor"),
        "provider_retention_policy": ai_router.provider_retention_policy(),
        "provider_regions": ai_router.provider_regions(),
    }
