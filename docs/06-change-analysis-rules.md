# MVP 变更分析规则说明

## 1. 目标

MVP 版变更分析器用于根据 changed files、单文件 diff 文本和全局 diff 文本，识别本次 MR 是否涉及以下变更：

- API
- API_ENDPOINT（规划中）
- API_REQUEST_SCHEMA（规划中）
- API_RESPONSE_SCHEMA（规划中）
- API_AUTH（规划中）
- API_ERROR_CONTRACT（规划中）
- DB（聚合类型）
- DB_SCHEMA
- DB_SQL
- ORM_MAPPING
- ENTITY_MODEL
- DATA_MIGRATION
- CACHE
- CACHE_KEY
- CACHE_TTL
- CACHE_INVALIDATION
- CACHE_READ_WRITE
- CACHE_SERIALIZATION
- MQ
- MQ_PRODUCER
- MQ_CONSUMER
- MQ_MESSAGE_SCHEMA
- MQ_TOPIC_CONFIG
- MQ_RETRY_DLQ
- CONFIG
- CONFIG_FEATURE_FLAG（规划中）
- CONFIG_DATASOURCE（规划中）
- CONFIG_MIDDLEWARE（规划中）
- CONFIG_SECURITY（规划中）
- CONFIG_ENVIRONMENT（规划中）

当前版本只使用启发式规则，不引入 AI、AST、调用图或复杂语义分析。设计重点是输出结构稳定、规则边界清晰、后续可替换为更强分析器。

## 2. 输入对象

统一输入对象为 `ChangeAnalysisRequest`：

```json
{
  "changedFiles": [
    {
      "path": "src/main/java/com/demo/order/OrderController.java",
      "oldPath": "src/main/java/com/demo/order/OrderController.java",
      "newPath": "src/main/java/com/demo/order/OrderController.java",
      "changeType": "MODIFIED",
      "diffText": "+ @GetMapping(\"/api/orders/{id}\")"
    }
  ],
  "diffText": "optional global diff text"
}
```

说明：

- 优先使用单文件 `diffText`。
- 如果单文件 `diffText` 为空，才使用全局 `diffText` 补充识别。
- 如果没有 changed files 但提供了全局 diff，会创建一个 `__global_diff__` 虚拟文件进行分析。

## 3. 输出对象

统一输出对象为 `ChangeAnalysisResult`：

```json
{
  "summary": "Analyzed 2 changed file(s); matched change types: API, DB.",
  "changedFileCount": 2,
  "changeTypes": ["API", "DB"],
  "changedFiles": [
    {
      "path": "src/main/java/com/demo/order/OrderController.java",
      "changeType": "MODIFIED",
      "matchedChangeTypes": ["API"]
    }
  ],
  "impactedResources": [],
  "evidences": []
}
```

输出重点：

- `changeTypes`：本次变更命中的类型集合。
- `changedFiles`：每个文件命中了哪些变更类型。
- `impactedResources`：受影响资源，如接口、表、缓存 key、MQ topic、配置 key。
- `evidences`：命中的证据，包含文件、片段、规则名称。

## 4. 规则扩展点

所有规则实现统一接口：`ChangeAnalysisRule`。

```java
public interface ChangeAnalysisRule {
    String code();
    Optional<RuleMatch> analyze(ChangedFile changedFile, String globalDiffText);
}
```

新增规则时只需要：

1. 实现 `ChangeAnalysisRule`。
2. 注册为 Spring Bean。
3. 返回标准 `RuleMatch`。

聚合服务 `ChangeAnalysisService` 不关心具体规则细节，只负责执行规则、合并命中结果、生成统一输出。

## 5. 识别逻辑

### 5.1 API

`API` 当前作为粗粒度类型使用。后续细分时仍保留 `API` 作为聚合兼容类型；只要命中 API 细分类型，分析结果应同时包含 `API`。

命中条件：

- 文件路径包含：`controller`、`endpoint`、`/api/`、`dto`、`request`、`response`。
- 或 diff 内容包含 Spring MVC 注解：
  - `@RequestMapping`
  - `@GetMapping`
  - `@PostMapping`
  - `@PutMapping`
  - `@DeleteMapping`
  - `@PatchMapping`
  - `@RestController`
  - `@Controller`

资源提取：

- 优先提取 mapping 注解中的 HTTP 方法和路径，例如 `GET /api/orders/{id}`。
- 无法提取时退化为文件路径。

#### 5.1.1 API 细分规划

| 细分类型 | 含义 | 典型命中条件 | 初始置信度 |
| --- | --- | --- | --- |
| `API_ENDPOINT` | 接口路径或 HTTP 方法变更 | `@GetMapping` / `@PostMapping` / `@RequestMapping` 路径、method、Controller 方法签名变化 | HIGH |
| `API_REQUEST_SCHEMA` | 入参契约变更 | request DTO 字段增删改、`@RequestParam` / `@PathVariable` / `@RequestBody` 变化、校验注解变化 | HIGH |
| `API_RESPONSE_SCHEMA` | 出参契约变更 | response DTO / VO 字段增删改、返回类型变化、序列化字段变化 | HIGH |
| `API_AUTH` | 鉴权或权限规则变更 | `@PreAuthorize`、角色权限、登录态、token、拦截器、安全配置变化 | HIGH |
| `API_ERROR_CONTRACT` | 错误码或异常契约变更 | error code、异常类型、全局异常处理、失败响应结构变化 | MEDIUM |

命中原则：

- 只改 Controller 路径或 HTTP method：优先命中 `API_ENDPOINT`。
- 只改 request / response DTO：优先命中 `API_REQUEST_SCHEMA` 或 `API_RESPONSE_SCHEMA`，不直接断言接口路径变化。
- 权限注解、拦截器、安全配置变化：命中 `API_AUTH`，建议安全和调用方联动 review。
- 错误码、异常映射或统一响应结构变化：命中 `API_ERROR_CONTRACT`。

组合风险：

- `API_ENDPOINT` + `API_REQUEST_SCHEMA`：提示调用方兼容风险，建议补接口契约测试。
- `API_RESPONSE_SCHEMA` + `API_ERROR_CONTRACT`：提示前端和下游解析兼容风险。
- `API_AUTH` + `CONFIG_FEATURE_FLAG`：提示权限开关和灰度配置一致性风险。

### 5.2 DB 聚合类型

`DB` 作为兼容聚合类型保留。只要命中 `DB_SCHEMA`、`DB_SQL`、`ORM_MAPPING`、`ENTITY_MODEL` 或 `DATA_MIGRATION`，分析结果会同时包含 `DB`，用于旧模板、汇总和粗粒度筛选。

但风险卡片应优先展示细分类型，不应把 Mapper XML 或 Entity 变更直接等同于表结构变更。

### 5.3 DB_SCHEMA

命中条件：

- 文件路径或内容体现 Flyway / Liquibase / migration / schema 变更。
- diff 内容包含 DDL 特征：
  - `create table`
  - `alter table`
  - `drop table`
  - `add column`
  - `drop column`
  - `modify column`
  - `create index`
  - `drop index`

资源提取：

- 优先提取表名，例如 `orders`。
- 无法提取时退化为 SQL 文件路径。

置信度：

- 初始置信度为 `HIGH`。

### 5.4 DB_SQL

命中条件：

- Mapper XML、SQL 文件或代码 diff 中包含 SQL 读写逻辑：
  - `select ... from`
  - `insert into`
  - `update ... set`
  - `delete from`
- 查询条件、join、order by、limit 或返回字段变化。

资源提取：

- 优先提取表名，例如 `orders`。
- 无法提取时退化为 SQL 文件路径。

置信度：

- 初始置信度为 `MEDIUM`。
- 仅修改 Mapper XML 的 SQL 时，不直接命中 `DB_SCHEMA`。

### 5.5 ORM_MAPPING

命中条件：

- MyBatis / ORM 映射结构变化：
  - `resultMap`
  - `<result ...>`
  - `<id ...>`
  - `column=`
  - `property=`
  - `@Table`
  - `@Column`
  - `@JoinColumn`

资源提取：

- 优先提取表名或字段片段。
- 无法提取时退化为 Mapper / Entity 文件路径。

置信度：

- 初始置信度为 `MEDIUM`。

### 5.6 ENTITY_MODEL

命中条件：

- Java Entity / DO / PO / domain model 字段增删改。
- ORM 注解变化：
  - `@Entity`
  - `@Table`
  - `@Column`
- 字段类型变化、字段名变化、序列化字段变化。

资源提取：

- 优先提取字段名。
- 无法提取时退化为实体类文件路径。

置信度：

- 初始置信度为 `MEDIUM`。
- 只命中实体字段变更时，提示确认 DB / Mapper 是否同步，但不直接断言表结构已变更。

### 5.7 DATA_MIGRATION

命中条件：

- migration 中包含数据修复、历史数据回填或状态值转换。
- migration 文件中出现 `insert into`、`update ... set`、`delete from`，且不是纯 DDL。
- diff 内容包含：
  - `backfill`
  - `migrate`
  - `数据修复`
  - `回填`
  - `历史数据`

资源提取：

- 优先提取表名。
- 无法提取时退化为 migration 文件路径。

置信度：

- 初始置信度为 `HIGH`。

### 5.8 DB 组合风险

以下组合需要在风险引擎中提升风险等级：

- `ENTITY_MODEL` + `ORM_MAPPING` + 未命中 `DB_SCHEMA`：
  - 输出“疑似实体、映射与数据库结构未同步”。
  - 建议确认是否遗漏 migration 或 DDL。
- `DB_SQL` + `CONFIG`：
  - 建议确认数据源、分页、开关或灰度配置是否影响 SQL 路径。
- `DB_SCHEMA` + `DATA_MIGRATION`：
  - 建议确认结构变更和数据回填的执行顺序、幂等性和回滚策略。

### 5.9 CACHE

`CACHE` 作为聚合兼容类型保留。只要命中缓存细分类型，分析结果会同时包含 `CACHE`，用于旧模板、汇总和粗粒度筛选。

命中条件：

- 文件路径包含：`cache`、`redis`、`caffeine`、`ehcache`。
- 或 diff 内容包含缓存特征：
  - `RedisTemplate`
  - `StringRedisTemplate`
  - `@Cacheable`
  - `@CacheEvict`
  - `@CachePut`
  - `cacheManager`
  - `opsForValue`
  - `expire(`
  - `delete(`

资源提取：

- 优先提取形如 `order:detail` 的缓存 key。
- 无法提取时退化为文件路径。

#### 5.9.1 CACHE 细分类型

| 细分类型 | 含义 | 典型命中条件 | 初始置信度 |
| --- | --- | --- | --- |
| `CACHE_KEY` | 缓存 key 命名或组成变更 | key 常量、prefix、拼接参数、租户/用户维度变化 | HIGH |
| `CACHE_TTL` | 过期时间或续期策略变更 | `expire`、TTL 配置、`@Cacheable` 过期配置、缓存续期逻辑变化 | MEDIUM |
| `CACHE_INVALIDATION` | 删除、刷新或失效策略变更 | `delete`、`evict`、`@CacheEvict`、更新后清理缓存逻辑变化 | HIGH |
| `CACHE_READ_WRITE` | 读写路径或缓存模式变更 | `opsForValue().get/set`、cache-aside、写穿、回源逻辑变化 | MEDIUM |
| `CACHE_SERIALIZATION` | 缓存值结构或序列化方式变更 | Redis serializer、JSON 字段、缓存 DTO 字段变化 | MEDIUM |

命中原则：

- key 组成变化优先命中 `CACHE_KEY`，并提示历史 key 兼容和清理策略。
- TTL 或续期逻辑变化命中 `CACHE_TTL`，不直接等同于一致性风险。
- 删除、刷新、`@CacheEvict` 变化命中 `CACHE_INVALIDATION`，优先提示脏数据风险。
- 缓存对象字段或序列化配置变化命中 `CACHE_SERIALIZATION`，提示旧缓存反序列化风险。

组合风险：

- `CACHE_KEY` + `CACHE_INVALIDATION`：提示新旧 key 并存、清理遗漏和命中率异常。
- `CACHE_READ_WRITE` + `DB_SQL`：提示数据库读写和缓存一致性风险。
- `CACHE_SERIALIZATION` + `API_RESPONSE_SCHEMA`：提示缓存对象和接口响应结构兼容风险。

### 5.10 MQ

`MQ` 作为聚合兼容类型保留。只要命中 MQ 细分类型，分析结果会同时包含 `MQ`，用于旧模板、汇总和粗粒度筛选。

命中条件：

- 文件路径包含：`mq`、`message`、`producer`、`consumer`、`listener`、`rocketmq`、`kafka`、`rabbit`。
- 或 diff 内容包含 MQ 特征：
  - `@RocketMQMessageListener`
  - `RocketMQTemplate`
  - `KafkaTemplate`
  - `@KafkaListener`
  - `RabbitTemplate`
  - `@RabbitListener`
  - `sendMessage`
  - `convertAndSend`
  - `topic`
  - `consumerGroup`
  - `rocketmq`
  - `kafka`
  - `rabbitmq`

资源提取：

- 优先提取 `topic = "xxx"`、`topics = "xxx"` 或 `destination = "xxx"`。
- 无法提取时退化为文件路径。

#### 5.10.1 MQ 细分类型

| 细分类型 | 含义 | 典型命中条件 | 初始置信度 |
| --- | --- | --- | --- |
| `MQ_PRODUCER` | 消息生产逻辑变更 | `RocketMQTemplate`、`KafkaTemplate`、`RabbitTemplate`、send/convertAndSend 变化 | HIGH |
| `MQ_CONSUMER` | 消息消费逻辑变更 | listener 注解、consumer method、消费业务逻辑变化 | HIGH |
| `MQ_MESSAGE_SCHEMA` | 消息体契约变更 | message DTO 字段增删改、序列化字段、事件版本变化 | HIGH |
| `MQ_TOPIC_CONFIG` | topic、tag、group、destination 配置变更 | topic/tag/consumerGroup/groupId/destination 变化 | HIGH |
| `MQ_RETRY_DLQ` | 重试、死信、ack 或异常处理变更 | retry、dead letter、ack/nack、异常捕获、幂等 key 变化 | HIGH |

命中原则：

- 发送 API 或 producer 类变化优先命中 `MQ_PRODUCER`。
- listener 注解或 consumer 类变化优先命中 `MQ_CONSUMER`。
- 消息 DTO / event payload 变化命中 `MQ_MESSAGE_SCHEMA`，不直接等同于 topic 配置变化。
- topic、tag、consumerGroup、destination 变化命中 `MQ_TOPIC_CONFIG`。
- ack、重试、死信、异常处理、幂等 key 变化命中 `MQ_RETRY_DLQ`。

组合风险：

- `MQ_PRODUCER` + `MQ_MESSAGE_SCHEMA` + 未命中 `MQ_CONSUMER`：提示生产者消息体变更但消费者未同步。
- `MQ_CONSUMER` + `MQ_RETRY_DLQ`：提示重复消费、重试风暴和死信堆积风险。
- `MQ_TOPIC_CONFIG` + `CONFIG_MIDDLEWARE`：提示代码 topic/group 与环境配置不一致。

### 5.11 CONFIG

`CONFIG` 当前作为粗粒度类型使用。后续细分时保留 `CONFIG` 作为聚合兼容类型；只要命中配置细分类型，分析结果应同时包含 `CONFIG`。

命中条件：

- 文件路径包含：`application.yml`、`application.yaml`、`application.properties`、`bootstrap.yml`、`bootstrap.yaml`、`nacos`、`config`、`.properties`、`.yaml`、`.yml`。
- 或 diff 内容包含配置特征：
  - `spring:`
  - `server:`
  - `datasource:`
  - `redis:`
  - `rocketmq:`
  - `kafka:`
  - `nacos`
  - `feature`
  - `enabled:`

资源提取：

- 优先提取 YAML / properties 的 key，例如 `order`、`feature.enabled`。
- 无法提取时退化为文件路径。

#### 5.11.1 CONFIG 细分规划

| 细分类型 | 含义 | 典型命中条件 | 初始置信度 |
| --- | --- | --- | --- |
| `CONFIG_FEATURE_FLAG` | 功能开关或灰度配置变更 | `feature.*`、`enabled`、灰度、开关、实验配置变化 | MEDIUM |
| `CONFIG_DATASOURCE` | 数据源、连接池或 SQL 相关配置变更 | `spring.datasource`、连接池、读写分离、事务配置变化 | HIGH |
| `CONFIG_MIDDLEWARE` | 中间件连接与客户端配置变更 | Redis、MQ、Nacos、Feign、HTTP client 配置变化 | HIGH |
| `CONFIG_SECURITY` | 安全、鉴权、跨域或密钥配置变更 | security、auth、token、cors、secret、白名单变化 | HIGH |
| `CONFIG_ENVIRONMENT` | 环境差异或部署参数变更 | profile、server port、logging、资源限制、环境变量映射变化 | MEDIUM |

命中原则：

- `enabled`、灰度、feature 前缀优先命中 `CONFIG_FEATURE_FLAG`。
- datasource、连接池、事务配置优先命中 `CONFIG_DATASOURCE`。
- redis、rocketmq、kafka、rabbit、nacos、feign 等优先命中 `CONFIG_MIDDLEWARE`。
- security、auth、token、cors、secret 等优先命中 `CONFIG_SECURITY`。
- profile、端口、日志、资源限制优先命中 `CONFIG_ENVIRONMENT`。

组合风险：

- `CONFIG_DATASOURCE` + `DB_SQL`：提示数据源、分页和 SQL 路径变化需要联动验证。
- `CONFIG_MIDDLEWARE` + `MQ_TOPIC_CONFIG`：提示 MQ 客户端和 topic/group 配置一致性风险。
- `CONFIG_SECURITY` + `API_AUTH`：提示鉴权策略和接口权限规则一致性风险。

## 6. 示例输入与输出

### 示例 1：API Controller

输入：

```json
{
  "path": "src/main/java/com/demo/order/OrderController.java",
  "diffText": "+ @GetMapping(\"/api/orders/{id}\")"
}
```

输出摘要：

```json
{
  "changeTypes": ["API"],
  "resourceType": "API",
  "resourceName": "GET /api/orders/{id}"
}
```

### 示例 2：API DTO

输入：

```json
{
  "path": "src/main/java/com/demo/order/dto/OrderResponse.java",
  "diffText": "+ private String payStatus;"
}
```

输出摘要：

```json
{
  "changeTypes": ["API"],
  "resourceType": "API",
  "resourceName": "src/main/java/com/demo/order/dto/OrderResponse.java"
}
```

### 示例 3：MyBatis SQL

输入：

```json
{
  "path": "src/main/resources/mapper/OrderMapper.xml",
  "diffText": "+ select id, status from orders where id = #{id}"
}
```

输出摘要：

```json
{
  "changeTypes": ["DB", "DB_SQL"],
  "resourceType": "DB_TABLE",
  "resourceName": "orders"
}
```

### 示例 4：数据库 migration

输入：

```json
{
  "path": "db/migration/V12__alter_orders.sql",
  "diffText": "+ alter table orders add column risk_level varchar(32)"
}
```

输出摘要：

```json
{
  "changeTypes": ["DB", "DB_SCHEMA"],
  "resourceType": "DB_TABLE",
  "resourceName": "orders"
}
```

### 示例 4.1：实体字段变更

输入：

```json
{
  "path": "src/main/java/com/demo/car/entity/Car.java",
  "diffText": "+ private String supportDeviceModel;"
}
```

输出摘要：

```json
{
  "changeTypes": ["DB", "ENTITY_MODEL"],
  "resourceType": "ENTITY_FIELD",
  "resourceName": "supportDeviceModel"
}
```

### 示例 4.2：MyBatis 映射变更

输入：

```json
{
  "path": "src/main/resources/mapper/CarMapper.xml",
  "diffText": "+ <result column=\"support_device_model\" property=\"supportDeviceModel\" />"
}
```

输出摘要：

```json
{
  "changeTypes": ["DB", "ORM_MAPPING"],
  "resourceType": "ORM_MAPPING",
  "resourceName": "CarMapper.xml"
}
```

### 示例 5：Redis 缓存 key

输入：

```json
{
  "path": "src/main/java/com/demo/order/OrderCacheService.java",
  "diffText": "+ redisTemplate.opsForValue().set(\"order:detail\" + id, value);"
}
```

输出摘要：

```json
{
  "changeTypes": ["CACHE", "CACHE_READ_WRITE"],
  "resourceType": "CACHE_KEY",
  "resourceName": "order:detail"
}
```

### 示例 6：Spring Cache 注解

输入：

```json
{
  "path": "src/main/java/com/demo/product/ProductService.java",
  "diffText": "+ @CacheEvict(value = \"product\", key = \"#id\")"
}
```

输出摘要：

```json
{
  "changeTypes": ["CACHE", "CACHE_INVALIDATION"],
  "resourceType": "CACHE_KEY",
  "resourceName": "src/main/java/com/demo/product/ProductService.java"
}
```

### 示例 7：RocketMQ 消费者

输入：

```json
{
  "path": "src/main/java/com/demo/order/OrderPaidConsumer.java",
  "diffText": "+ @RocketMQMessageListener(topic = \"order-paid-topic\", consumerGroup = \"order-service\")"
}
```

输出摘要：

```json
{
  "changeTypes": ["MQ", "MQ_CONSUMER"],
  "resourceType": "MQ_CONSUMER",
  "resourceName": "order-paid-topic"
}
```

### 示例 8：Kafka 生产者

输入：

```json
{
  "path": "src/main/java/com/demo/order/OrderEventProducer.java",
  "diffText": "+ kafkaTemplate.send(\"order-event-topic\", payload);"
}
```

输出摘要：

```json
{
  "changeTypes": ["MQ", "MQ_PRODUCER"],
  "resourceType": "MQ_PRODUCER",
  "resourceName": "order-event-topic"
}
```

### 示例 9：应用配置

输入：

```json
{
  "path": "src/main/resources/application.yml",
  "diffText": "+ order:\n+   feature-enabled: true"
}
```

输出摘要：

```json
{
  "changeTypes": ["CONFIG"],
  "resourceType": "CONFIG_KEY",
  "resourceName": "order"
}
```

### 示例 10：Nacos 配置

输入：

```json
{
  "path": "config/nacos/order-service.yaml",
  "diffText": "+ risk-review:\n+   enabled: true"
}
```

输出摘要：

```json
{
  "changeTypes": ["CONFIG"],
  "resourceType": "CONFIG_KEY",
  "resourceName": "risk-review"
}
```

### 示例 11：同一 MR 多类型变更

输入：

```json
{
  "changedFiles": [
    {
      "path": "src/main/java/com/demo/order/OrderController.java",
      "diffText": "+ @PostMapping(\"/api/orders\")"
    },
    {
      "path": "src/main/resources/mapper/OrderMapper.xml",
      "diffText": "+ update orders set status = #{status}"
    },
    {
      "path": "src/main/resources/application.yml",
      "diffText": "+ rocketmq:\n+   name-server: localhost:9876"
    }
  ]
}
```

输出摘要：

```json
{
  "changeTypes": ["API", "DB", "MQ", "CONFIG"],
  "changedFileCount": 3
}
```

## 7. 已知限制

- 不能理解 Java AST、XML AST 或 YAML 层级语义。
- 不能确认 API 字段是否真的不兼容，只能识别“可能涉及接口变更”。
- 不能从 GitLab MR webhook 自动获取完整 diff，仍需要上游传入 changed files 或后续接入 GitLab API。
- 同一个文件可能命中多个类型，例如 `application.yml` 中修改 `rocketmq` 配置会同时命中 CONFIG 和 MQ。
- 当前规则偏召回，风险引擎阶段还需要根据上下文降低误报。
