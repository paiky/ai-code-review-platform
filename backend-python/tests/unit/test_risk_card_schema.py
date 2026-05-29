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
        ["DB_DATA_WRITE_CHANGE_CHECK", "CONFIG_RELEASE_CHECK"],
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
    assert item["ruleCode"] == "DB_DATA_WRITE_CHANGE_CHECK"
    assert item["category"] == "DB_DATA_WRITE"
    artifact = item["maintenanceArtifacts"][0]
    assert artifact["artifactType"] == "SQL"
    assert artifact["confidence"] == "EXACT"
    assert "alter table orders add column risk_level varchar(32);" in artifact["content"]
    assert card["focusIndicators"][0]["code"] == "DB_SCHEMA_CHANGE"


def test_db_card_ignores_select_only_and_extracts_write_sql_without_xml_tags() -> None:
    analysis = analyze_changes(
        [
            {
                "path": "src/main/resources/mapper/OrderMapper.xml",
                "diffText": (
                    "@@ -1,4 +1,8 @@\n"
                    " </select>\n"
                    "+ <update id=\"updateStatus\">\n"
                    "+ update orders set status = #{status} where id = #{id}\n"
                    "+ </update>\n"
                    "+ <select id=\"queryIds\">\n"
                    "+ select id from orders\n"
                    "+ </select>"
                ),
            },
            {
                "path": "src/main/resources/mapper/ReadOnlyMapper.xml",
                "diffText": "+ select id, status from orders where id = #{id}",
            },
        ]
    )

    card = generate_risk_card(analysis, ["DB_DATA_WRITE_CHANGE_CHECK"])

    artifact = card["riskItems"][0]["maintenanceArtifacts"][0]
    assert "update orders set status = #{status} where id = #{id};" in artifact["content"]
    assert "select id from orders" not in artifact["content"].lower()
    assert "</select>" not in artifact["content"]
    assert "<update" not in artifact["content"]


def test_added_entity_with_table_name_generates_inferred_create_table_draft() -> None:
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
                    "+ }"
                ),
            }
        ]
    )

    card = generate_risk_card(analysis, ["DB_DATA_WRITE_CHANGE_CHECK"])

    artifact = card["riskItems"][0]["maintenanceArtifacts"][0]
    assert artifact["confidence"] == "INFERRED"
    assert "CREATE TABLE client_fence_learning_model" in artifact["content"]
    assert "id bigint NULL" in artifact["content"]
    assert "user_id bigint NULL" in artifact["content"]
    assert "avg_minute decimal(18,2) NULL" in artifact["content"]


def test_field_fill_insert_annotation_does_not_generate_exact_sql() -> None:
    analysis = analyze_changes(
        [
            {
                "path": "src/main/java/com/demo/car/entity/FenceLearningModel.java",
                "changeType": "ADDED",
                "diffText": (
                    '+ @TableName("client_fence_learning_model")\n'
                    '+ public class FenceLearningModel {\n'
                    '+   @TableId(value = "id", type = IdType.ASSIGN_ID)\n'
                    '+   private Long id;\n'
                    '+   @TableField(value = "create_time", fill = FieldFill.INSERT)\n'
                    '+   private Date createTime;\n'
                    "+ }"
                ),
            }
        ]
    )

    card = generate_risk_card(analysis, ["DB_DATA_WRITE_CHANGE_CHECK"])

    artifact = card["riskItems"][0]["maintenanceArtifacts"][0]
    assert artifact["confidence"] == "INFERRED"
    assert "CREATE TABLE client_fence_learning_model" in artifact["content"]
    assert "@TableField" not in artifact["content"]
    assert "create_time datetime NULL" in artifact["content"]


def test_modified_entity_generates_inferred_alter_table_draft() -> None:
    analysis = analyze_changes(
        [
            {
                "path": "src/main/java/com/demo/car/entity/FenceLearningModel.java",
                "changeType": "MODIFIED",
                "diffText": (
                    '+ @TableName("client_fence_learning_model")\n'
                    '+ @TableField("support_device_model")\n'
                    "+ private String supportDeviceModel;"
                ),
            }
        ]
    )

    card = generate_risk_card(analysis, ["DB_DATA_WRITE_CHANGE_CHECK"])

    artifact = card["riskItems"][0]["maintenanceArtifacts"][0]
    assert artifact["confidence"] == "INFERRED"
    assert "ALTER TABLE client_fence_learning_model ADD COLUMN support_device_model varchar(255) NULL;" in artifact["content"]
    assert "CREATE TABLE" not in artifact["content"]


def test_risk_card_generates_cache_mq_and_config_artifacts() -> None:
    analysis = analyze_changes(
        [
            {
                "path": "src/main/java/com/demo/order/OrderCacheService.java",
                "diffText": (
                    '+ redisTemplate.opsForValue().get("order:detail:" + id);\n'
                    '+ redisTemplate.opsForValue().set("order:detail:" + id, value);\n'
                    '+ redisTemplate.expire("order:detail:" + id, Duration.ofMinutes(5));\n'
                    '+ redisTemplate.delete("order:list");'
                ),
            },
            {
                "path": "src/main/java/com/demo/order/RabbitMqBindingConfig.java",
                "diffText": (
                    '+ public static final String ORDER_EXCHANGE = "order.exchange";\n'
                    '+ public static final String ORDER_QUEUE = "order.queue";\n'
                    '+ public static final String ORDER_ROUTING_KEY = "order.route";\n'
                    '+ return new Queue(ORDER_QUEUE, true, false, false);'
                ),
            },
            {
                "path": "config/nacos/order-service.yaml",
                "diffText": "+ risk-review:\n+   enabled: true",
            },
            {
                "path": "src/main/java/com/demo/order/OrderProperties.java",
                "diffText": '+ @Value("${order.confirm.enabled:false}")',
            },
        ]
    )

    card = generate_risk_card(
        analysis,
        [
            "CACHE_WRITE_DELETE_CHANGE_CHECK",
            "MQ_CONFIG_CHANGE_CHECK",
            "CONFIG_RELEASE_CHECK",
        ],
    )

    artifacts = [
        artifact
        for item in card["riskItems"]
        for artifact in item["maintenanceArtifacts"]
    ]
    assert any(
        artifact["artifactType"] == "REDIS_COMMAND"
        and "Redis 配置变更信息：" in artifact["content"]
        and "order:detail:" in artifact["content"]
        and "order:list" in artifact["content"]
        and "GET " not in artifact["content"]
        for artifact in artifacts
    )
    assert any(
        artifact["artifactType"] == "MQ_CONFIG_CODE"
        and "- Exchange: order.exchange" in artifact["content"]
        and "- Queue: order.queue" in artifact["content"]
        and "- RouteKey: order.route" in artifact["content"]
        and "String topic" not in artifact["content"]
        for artifact in artifacts
    )
    assert any(artifact["artifactType"] == "NACOS_CONFIG" and "risk-review:" in artifact["content"] for artifact in artifacts)
    assert any(artifact["artifactType"] == "NACOS_CONFIG" and "order.confirm.enabled: false" in artifact["content"] for artifact in artifacts)


def test_mq_artifact_summarizes_binding_config_without_placeholder_code() -> None:
    analysis = analyze_changes(
        [
            {
                "path": "src/main/java/com/demo/order/RabbitMqBindingConfig.java",
                "diffText": (
                    "+    @Bean\n"
                    "+    public TopicExchange reportPositionExchange() {\n"
                    "+        return new TopicExchange(MqClientConstant.REPORT_POSITION_EXCHANGE, false, false);\n"
                    "+    }\n"
                    "+    @Bean\n"
                    "+    public Queue reportPositionQueue() {\n"
                    "+        return new Queue(MqClientConstant.REPORT_POSITION_QUEUE, true, false, false);\n"
                    "+    }\n"
                    "+    @Bean\n"
                    "+    public Binding reportPositionBinding() {\n"
                    "+        return BindingBuilder.bind(reportPositionQueue())\n"
                    "+                .to(reportPositionExchange())\n"
                    "+                .with(MqClientConstant.REPORT_POSITION_ROUTING_KEY);\n"
                    "+    }\n"
                    "+    @Bean\n"
                    "+    public Queue reportProcessQueue() {\n"
                    "+        return new Queue(MqClientConstant.REPORT_PROCESS_QUEUE, true, false, false);\n"
                    "+    }\n"
                    "+    @Bean\n"
                    "+    public Binding reportProcessBinding() {\n"
                    "+        return BindingBuilder.bind(reportProcessQueue())\n"
                    "+                .to(reportPositionExchange())\n"
                    "+                .with(MqClientConstant.REPORT_PROCESS_ROUTING_KEY);\n"
                    "+    }\n"
                ),
            }
        ]
    )

    card = generate_risk_card(analysis, ["MQ_CONFIG_CHANGE_CHECK"])

    artifact = card["riskItems"][0]["maintenanceArtifacts"][0]
    assert artifact["title"] == "MQ 配置 Java 代码"
    assert artifact["language"] == "java"
    assert "String topic" not in artifact["content"]
    assert "<queue>" not in artifact["content"]
    assert "// MQ" not in artifact["content"]
    assert "public TopicExchange reportPositionExchange() {" in artifact["content"]
    assert "return new Queue(MqClientConstant.REPORT_POSITION_QUEUE, true, false, false);" in artifact["content"]
    assert "public Binding reportPositionBinding() {" in artifact["content"]
    assert ".with(MqClientConstant.REPORT_PROCESS_ROUTING_KEY);" in artifact["content"]


def test_redis_artifact_summarizes_keys_and_relevant_code_only() -> None:
    analysis = analyze_changes(
        [
            {
                "path": "src/main/java/com/demo/report/AutoReportQualityUserJob.java",
                "diffText": (
                    '+ public static final String REDIS_POI_ARRIVE_TIME = "poiArriveTime";\n'
                    '+ public static final String REDIS_LAST_POI_NAME = "lastPoiName";\n'
                    '+ import com.demo.RedisConstant;\n'
                    '+ private IRedisService redisService;\n'
                    '+ boolean locked = redissonUtils.tryLockWithDog(LOCK_KEY, 100, 120_000);\n'
                    '+ log.info("AutoReportQualityUserJob：未查询到符合条件的优质用户，清空 Redis Set");\n'
                    '+ redisService.del(RedisConstant.AUTO_REPORT_QUALITY_USER_SET);\n'
                    '+ String setKey = RedisConstant.AUTO_REPORT_QUALITY_USER_SET;\n'
                    '+ redisService.del(setKey);\n'
                    '+ redisService.sadd(setKey, String.valueOf(userId));'
                ),
            }
        ]
    )

    card = generate_risk_card(analysis, ["CACHE_WRITE_DELETE_CHANGE_CHECK"])

    artifact = card["riskItems"][0]["maintenanceArtifacts"][0]
    assert artifact["title"] == "Redis Java 代码"
    assert artifact["language"] == "java"
    assert "REDIS_POI_ARRIVE_TIME" not in artifact["content"]
    assert "String setKey = RedisConstant.AUTO_REPORT_QUALITY_USER_SET;" not in artifact["content"]
    assert "redisService.del(setKey);" in artifact["content"]
    assert "redisService.sadd(setKey, String.valueOf(userId));" in artifact["content"]
    assert "import com.demo.RedisConstant" not in artifact["content"]
    assert "private IRedisService" not in artifact["content"]
    assert "redissonUtils.tryLockWithDog" not in artifact["content"]
    assert "log.info" not in artifact["content"]


def test_config_artifacts_split_yaml_and_java_value_sources() -> None:
    analysis = analyze_changes(
        [
            {
                "path": "config/nacos/order-service.yaml",
                "diffText": "+ risk-review:\n+   enabled: true",
            },
            {
                "path": "src/main/java/com/demo/order/OrderProperties.java",
                "diffText": (
                    '+ @Value("${order.confirm.enabled:false}")\n'
                    '+ private boolean confirmEnabled;\n'
                    '+ targetUser = clientUserService.getByUserId(dto.getTargetUserId());'
                ),
            },
        ]
    )

    card = generate_risk_card(analysis, ["CONFIG_RELEASE_CHECK"])

    artifacts = card["riskItems"][0]["maintenanceArtifacts"]
    assert len(artifacts) == 2
    yaml_artifact = next(artifact for artifact in artifacts if artifact["language"] == "yaml")
    java_value_artifact = next(artifact for artifact in artifacts if artifact["sourceFilePath"].endswith(".java"))
    assert "risk-review:" in yaml_artifact["content"]
    assert "  enabled: true" in yaml_artifact["content"]
    assert java_value_artifact["language"] == "yaml"
    assert java_value_artifact["content"] == "order.confirm.enabled: false"
    assert "targetUser" not in java_value_artifact["content"]
