from app.change_analysis.service import analyze_changes


def test_db_rule_detects_write_schema_entity_and_mapping_but_ignores_select_only() -> None:
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
            {
                "path": "src/main/resources/mapper/WriteMapper.xml",
                "diffText": "+ update orders set status = #{status} where id = #{id}",
            },
        ]
    )

    assert {"DB", "DB_DATA_WRITE"}.issubset(set(analysis["changeTypes"]))
    assert "DB_SQL" not in analysis["changeTypes"]


def test_mq_and_cache_rules_focus_on_config_and_write_delete() -> None:
    analysis = analyze_changes(
        [
            {
                "path": "src/main/java/com/demo/order/OrderCacheService.java",
                "diffText": (
                    '+ redisTemplate.opsForValue().get("order:detail:" + id);\n'
                    '+ redisTemplate.opsForValue().set("order:detail:" + id, value);'
                ),
            },
            {
                "path": "src/main/java/com/demo/order/OrderPaidConsumer.java",
                "diffText": '+ @RocketMQMessageListener(topic = "order-paid-topic", consumerGroup = "order-service")',
            },
            {
                "path": "src/main/java/com/demo/order/RabbitMqBindingConfig.java",
                "diffText": '+ return new Queue("order-paid-queue", true, false, false);\n+ .with("order-paid-route");',
            },
        ]
    )

    assert "CACHE_WRITE_DELETE" in analysis["changeTypes"]
    assert "MQ_CONFIG" in analysis["changeTypes"]
    assert "MQ_CONSUMER" not in analysis["changeTypes"]
    assert "CACHE" in analysis["changeTypes"]
    assert "MQ" in analysis["changeTypes"]


def test_read_only_cache_and_mq_consumer_do_not_match() -> None:
    analysis = analyze_changes(
        [
            {
                "path": "src/main/java/com/demo/order/OrderCacheService.java",
                "diffText": '+ redisTemplate.opsForValue().get("order:detail:" + id);',
            },
            {
                "path": "src/main/java/com/demo/order/OrderPaidConsumer.java",
                "diffText": '+ @RocketMQMessageListener(topic = "order-paid-topic", consumerGroup = "order-service")',
            },
        ]
    )

    assert "CACHE" not in analysis["changeTypes"]
    assert "MQ" not in analysis["changeTypes"]
