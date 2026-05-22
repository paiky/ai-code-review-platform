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
        "maintenanceArtifacts",
    ]:
        assert field in item
    assert item["category"] == "DB_SCHEMA"
    artifact = item["maintenanceArtifacts"][0]
    assert artifact["artifactType"] == "SQL"
    assert artifact["confidence"] == "EXACT"
    assert "alter table orders add column risk_level varchar(32);" in artifact["content"]
    assert card["focusIndicators"][0]["code"] == "DB_SCHEMA_CHANGE"


def test_risk_card_generates_inferred_sql_for_entity_and_mapping_without_ddl() -> None:
    analysis = analyze_changes(
        [
            {
                "path": "src/main/java/com/demo/car/entity/Car.java",
                "diffText": "+ private String supportDeviceModel;",
            },
            {
                "path": "src/main/resources/mapper/CarMapper.xml",
                "diffText": '+ <result column="support_device_model" property="supportDeviceModel" />',
            },
        ]
    )

    card = generate_risk_card(
        analysis,
        ["ENTITY_MODEL_CHANGE_CHECK", "ORM_MAPPING_CHANGE_CHECK", "DB_SCHEMA_SYNC_SUSPECT_CHECK"],
    )

    sync_item = next(item for item in card["riskItems"] if item["ruleCode"] == "DB_SCHEMA_SYNC_SUSPECT_CHECK")
    artifact = sync_item["maintenanceArtifacts"][0]
    assert artifact["artifactType"] == "SQL"
    assert artifact["confidence"] == "INFERRED"
    assert "ALTER TABLE <table_name> ADD COLUMN support_device_model varchar(255) NULL;" in artifact["content"]
    assert "确认新增表还是已有表改字段" in artifact["notes"]


def test_added_entity_with_table_name_generates_create_table_draft() -> None:
    analysis = analyze_changes(
        [
            {
                "path": "src/main/java/com/demo/car/entity/FenceLearningModel.java",
                "changeType": "ADDED",
                "diffText": (
                    '+ @TableName("client_fence_learning_model")\n'
                    '+ public class FenceLearningModel {\n'
                    '+   @TableId(value = "id")\n'
                    '+   private Long id;\n'
                    '+   @TableField("user_id")\n'
                    '+   private Long userId;\n'
                    '+   @TableField("avg_minute")\n'
                    '+   private BigDecimal avgMinute;\n'
                    '+ }'
                ),
            }
        ]
    )

    card = generate_risk_card(analysis, ["ENTITY_MODEL_CHANGE_CHECK"])

    artifact = card["riskItems"][0]["maintenanceArtifacts"][0]
    assert artifact["title"] == "推断建表 SQL 草稿"
    assert artifact["confidence"] == "INFERRED"
    assert "CREATE TABLE client_fence_learning_model" in artifact["content"]
    assert "id bigint NULL" in artifact["content"]
    assert "user_id bigint NULL" in artifact["content"]
    assert "avg_minute decimal(18,2) NULL" in artifact["content"]
    assert "ALTER TABLE" not in artifact["content"]


def test_modified_entity_generates_alter_table_draft() -> None:
    analysis = analyze_changes(
        [
            {
                "path": "src/main/java/com/demo/car/entity/FenceLearningModel.java",
                "changeType": "MODIFIED",
                "diffText": (
                    '+ @TableName("client_fence_learning_model")\n'
                    '+ @TableField("support_device_model")\n'
                    '+ private String supportDeviceModel;'
                ),
            }
        ]
    )

    card = generate_risk_card(analysis, ["ENTITY_MODEL_CHANGE_CHECK"])

    artifact = card["riskItems"][0]["maintenanceArtifacts"][0]
    assert artifact["title"] == "推断改表 SQL 草稿"
    assert "ALTER TABLE client_fence_learning_model ADD COLUMN support_device_model varchar(255) NULL;" in artifact["content"]
    assert "CREATE TABLE" not in artifact["content"]


def test_two_added_entities_generate_separate_create_table_artifacts() -> None:
    analysis = analyze_changes(
        [
            {
                "path": "src/main/java/com/demo/entity/FenceLearningModel.java",
                "changeType": "ADDED",
                "diffText": (
                    '+ @TableName("client_fence_learning_model")\n'
                    '+ public class FenceLearningModel {\n'
                    '+   @TableId(value = "id")\n'
                    '+   private Long id;\n'
                    '+   @TableField("fence_id")\n'
                    '+   private Long fenceId;\n'
                    '+ }'
                ),
            },
            {
                "path": "src/main/java/com/demo/entity/ClientReportMessage.java",
                "changeType": "ADDED",
                "diffText": (
                    '+ @TableName("client_report_message")\n'
                    '+ public class ClientReportMessage {\n'
                    '+   @TableId(value = "id")\n'
                    '+   private Long id;\n'
                    '+   @TableField("message_type")\n'
                    '+   private Integer messageType;\n'
                    '+ }'
                ),
            },
        ]
    )

    card = generate_risk_card(analysis, ["ENTITY_MODEL_CHANGE_CHECK"])

    artifacts = card["riskItems"][0]["maintenanceArtifacts"]
    assert len(artifacts) == 2
    first, second = [artifact["content"] for artifact in artifacts]
    assert "CREATE TABLE client_fence_learning_model" in first
    assert "fence_id bigint NULL" in first
    assert "message_type" not in first
    assert "CREATE TABLE client_report_message" in second
    assert "message_type int NULL" in second
    assert "fence_id" not in second


def test_exact_schema_sql_suppresses_inferred_entity_sql() -> None:
    analysis = analyze_changes(
        [
            {
                "path": "db/migration/V12__create_car.sql",
                "changeType": "ADDED",
                "diffText": "+ create table car (id bigint primary key, support_device_model varchar(255));",
            },
            {
                "path": "src/main/java/com/demo/car/entity/Car.java",
                "changeType": "ADDED",
                "diffText": (
                    '+ @TableName("car")\n'
                    '+ public class Car {\n'
                    '+   @TableField("support_device_model")\n'
                    '+   private String supportDeviceModel;\n'
                    '+ }'
                ),
            },
        ]
    )

    card = generate_risk_card(analysis, ["DB_SCHEMA_CHANGE_CHECK", "ENTITY_MODEL_CHANGE_CHECK"])

    schema_item = next(item for item in card["riskItems"] if item["ruleCode"] == "DB_SCHEMA_CHANGE_CHECK")
    entity_item = next(item for item in card["riskItems"] if item["ruleCode"] == "ENTITY_MODEL_CHANGE_CHECK")
    assert schema_item["maintenanceArtifacts"][0]["confidence"] == "EXACT"
    assert "create table car" in schema_item["maintenanceArtifacts"][0]["content"]
    assert entity_item["maintenanceArtifacts"] == []


def test_exact_schema_sql_only_suppresses_matching_table() -> None:
    analysis = analyze_changes(
        [
            {
                "path": "db/migration/V12__create_car.sql",
                "changeType": "ADDED",
                "diffText": "+ create table car (id bigint primary key);",
            },
            {
                "path": "src/main/java/com/demo/entity/OrderEvent.java",
                "changeType": "ADDED",
                "diffText": (
                    '+ @TableName("order_event")\n'
                    '+ public class OrderEvent {\n'
                    '+   @TableField("event_id")\n'
                    '+   private Long eventId;\n'
                    '+ }'
                ),
            },
        ]
    )

    card = generate_risk_card(analysis, ["DB_SCHEMA_CHANGE_CHECK", "ENTITY_MODEL_CHANGE_CHECK"])

    entity_item = next(item for item in card["riskItems"] if item["ruleCode"] == "ENTITY_MODEL_CHANGE_CHECK")
    assert len(entity_item["maintenanceArtifacts"]) == 1
    assert "CREATE TABLE order_event" in entity_item["maintenanceArtifacts"][0]["content"]


def test_risk_card_generates_cache_mq_and_config_artifacts() -> None:
    analysis = analyze_changes(
        [
            {
                "path": "src/main/java/com/demo/order/OrderCacheService.java",
                "diffText": (
                    '+ redisTemplate.opsForValue().set("order:detail:" + id, value);\n'
                    '+ redisTemplate.expire("order:detail:" + id, Duration.ofMinutes(5));\n'
                    '+ redisTemplate.delete("order:list");'
                ),
            },
            {
                "path": "src/main/java/com/demo/order/OrderPaidConsumer.java",
                "diffText": '+ @RocketMQMessageListener(topic = "order-paid-topic", consumerGroup = "order-service")',
            },
            {
                "path": "config/nacos/order-service.yaml",
                "diffText": "+ risk-review:\n+   enabled: true",
            },
        ]
    )

    card = generate_risk_card(
        analysis,
        [
            "CACHE_READ_WRITE_CHANGE_CHECK",
            "CACHE_TTL_CHANGE_CHECK",
            "CACHE_INVALIDATION_CHANGE_CHECK",
            "MQ_CONSUMER_CHANGE_CHECK",
            "CONFIG_RELEASE_CHECK",
        ],
    )

    artifacts = [
        artifact
        for item in card["riskItems"]
        for artifact in item["maintenanceArtifacts"]
    ]
    assert any(artifact["artifactType"] == "REDIS_COMMAND" and "SET order:detail:" in artifact["content"] for artifact in artifacts)
    assert any(artifact["artifactType"] == "MQ_CONFIG_CODE" and 'String topic = "order-paid-topic";' in artifact["content"] for artifact in artifacts)
    assert any(artifact["artifactType"] == "NACOS_CONFIG" and "risk-review:" in artifact["content"] for artifact in artifacts)
    assert any(artifact["artifactType"] == "NACOS_CONFIG" and "  enabled: true" in artifact["content"] for artifact in artifacts)
