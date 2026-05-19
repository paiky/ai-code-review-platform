from app.change_analysis.service import analyze_changes


def test_db_fine_grained_rules_detect_sql_schema_and_sync_suspect() -> None:
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
            {
                "path": "src/main/resources/mapper/OrderMapper.xml",
                "diffText": "+ select id, status from orders where id = #{id}",
            },
        ]
    )

    assert {"DB", "ENTITY_MODEL", "ORM_MAPPING", "DB_SQL"}.issubset(set(analysis["changeTypes"]))


def test_mq_and_cache_fine_grained_rules() -> None:
    analysis = analyze_changes(
        [
            {
                "path": "src/main/java/com/demo/order/OrderCacheService.java",
                "diffText": '+ redisTemplate.opsForValue().set("order:detail:" + id, value);',
            },
            {
                "path": "src/main/java/com/demo/order/OrderPaidConsumer.java",
                "diffText": '+ @RocketMQMessageListener(topic = "order-paid-topic", consumerGroup = "order-service")',
            },
        ]
    )

    assert "CACHE_READ_WRITE" in analysis["changeTypes"]
    assert "MQ_CONSUMER" in analysis["changeTypes"]
    assert "CACHE" in analysis["changeTypes"]
    assert "MQ" in analysis["changeTypes"]

