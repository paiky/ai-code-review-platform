from app.change_analysis.service import analyze_changes
from app.risk_engine.service import generate_risk_card


def test_risk_card_schema_contains_required_top_level_and_item_fields() -> None:
    analysis = analyze_changes(
        [
            {
                "path": "db/migration/V12__alter_orders.sql",
                "diffText": "+ alter table orders add column risk_level varchar(32)",
            }
        ]
    )

    card = generate_risk_card(
        analysis,
        ["DB_SCHEMA_CHANGE_CHECK", "CONFIG_RELEASE_CHECK"],
        ["确认变更影响范围。"],
    )

    for field in [
        "cardId",
        "summary",
        "riskLevel",
        "affectedResources",
        "focusIndicators",
        "riskItems",
        "recommendedChecks",
        "suggestedReviewRoles",
        "generatedAt",
        "generator",
    ]:
        assert field in card
    item = card["riskItems"][0]
    for field in [
        "riskId",
        "ruleCode",
        "category",
        "riskLevel",
        "title",
        "description",
        "affectedResources",
        "evidences",
        "recommendedChecks",
        "suggestedReviewRoles",
        "relatedSignals",
    ]:
        assert field in item
    assert item["category"] == "DB_SCHEMA"
    assert card["focusIndicators"][0]["code"] == "DB_SCHEMA_CHANGE"

