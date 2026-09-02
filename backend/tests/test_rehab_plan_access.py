import os
from types import SimpleNamespace

from fastapi.testclient import TestClient

os.environ.setdefault("MONGO_URL", "mongodb://127.0.0.1:27017")
os.environ.setdefault("DB_NAME", "axonai_rehab_plan_access_test")

from backend import server


class AssessmentStore:
    def __init__(self, *documents):
        self.documents = {document["id"]: dict(document) for document in documents}

    async def find_one(self, query, *_args, **_kwargs):
        document = self.documents.get(query.get("id"))
        if not document or document.get("user_id") != query.get("user_id"):
            return None
        return dict(document)

    async def update_one(self, query, update):
        document = self.documents.get(query.get("id"))
        if not document or document.get("user_id") != query.get("user_id"):
            return SimpleNamespace(modified_count=0)
        if query.get("rehab_plan_first_viewed_at") == {"$exists": False} and "rehab_plan_first_viewed_at" in document:
            return SimpleNamespace(modified_count=0)
        document.update(update["$set"])
        return SimpleNamespace(modified_count=1)


def test_rehab_plan_preparation_is_claimed_once_per_account_assessment(monkeypatch):
    user_id = "u_plan_access"
    assessment_id = "assessment-plan-access"
    assessment = {"id": assessment_id, "user_id": user_id}
    next_assessment_id = "assessment-plan-access-next"
    store = AssessmentStore(assessment, {"id": next_assessment_id, "user_id": user_id})

    async def signed_in_user(_headers):
        return {"id": user_id, "consent": {"health_data_consent": True}}

    monkeypatch.setattr(server, "_user_from_header", signed_in_user)
    monkeypatch.setattr(server, "db", SimpleNamespace(assessments=store))
    with TestClient(server.app) as client:
        first = client.post(f"/api/assessment/{assessment_id}/rehab-plan-access")
        second = client.post(f"/api/assessment/{assessment_id}/rehab-plan-access")
        later_assessment = client.post(f"/api/assessment/{next_assessment_id}/rehab-plan-access")

    assert first.status_code == 200
    assert first.json()["first_access"] is True
    assert first.json()["first_viewed_at"]
    assert second.status_code == 200
    assert second.json()["first_access"] is False
    assert second.json()["first_viewed_at"] == first.json()["first_viewed_at"]
    assert later_assessment.status_code == 200
    assert later_assessment.json()["first_access"] is True
