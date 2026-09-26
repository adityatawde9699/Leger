from app.services.ai_budget import AIRequestBudget


def test_budget_limits_requests_per_provider():
    budget = AIRequestBudget(global_limit=2)
    assert budget.allow("Groq")
    assert budget.allow("Groq")
    assert not budget.allow("Groq")


def test_provider_budget_overrides_global_budget():
    budget = AIRequestBudget(global_limit=3, provider_limits='{"Gemini": 1}')
    assert budget.allow("Groq")
    assert budget.allow("Groq")
    assert budget.allow("Groq")
    assert budget.allow("Gemini")
    assert not budget.allow("Gemini")
