"""Tests for goal creation and progress tracking."""

from .conftest import AUTH_HEADER


def test_create_and_complete_goal(client):
    r = client.post(
        "/goals",
        json={
            "name": "Emergency fund",
            "goal_type": "emergency_fund",
            "target_amount": "100000",
            "current_amount": "25000",
            "deadline": "2027-01-01",
        },
        headers=AUTH_HEADER,
    )
    assert r.status_code == 201
    goal = r.json()
    assert goal["status"] == "active"
    assert float(goal["target_amount"]) == 100000

    r = client.put(
        f"/goals/{goal['id']}",
        json={
            "name": "Emergency fund",
            "goal_type": "emergency_fund",
            "target_amount": "100000",
            "current_amount": "100000",
            "deadline": "2027-01-01",
            "status": "active",
        },
        headers=AUTH_HEADER,
    )
    assert r.status_code == 200
    assert r.json()["status"] == "completed"
