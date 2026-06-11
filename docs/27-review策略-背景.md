我会把它当成一个“反馈闭环 + 项目知识沉淀 + 模型评测治理”的系统能力来设计，而不是单纯做一个“误判按钮”。我先对业界常见做法做一点核对，再给你一版可落地的产品/技术方案。

已思考 5s

你的这个功能，**不要只理解成“误判标记”**，更适合定义为：

> **AI Review 反馈闭环能力：把用户对风险点的处理结果沉淀为项目组知识、规则、评测样本和模型策略，让平台越用越贴合团队规范。**

这块做好后，会是你平台和普通“AI 扫描代码工具”的核心差异点。

------

## 一、核心判断：不要直接拿用户反馈去改初始 Prompt

你担心的第 1 点非常关键：**不同模型输出风险点不一样，如果只为了修正某个模型的问题而改全局 Prompt，确实可能影响其他模型的判断。**

业界比较稳妥的做法不是“用户点一次误判就改 Prompt”，而是建立一套分层机制：

```
用户反馈
  ↓
反馈归类 / 质量判断
  ↓
进入项目知识库 / 规则库 / 评测集
  ↓
离线评估
  ↓
灰度发布到某个项目组、某个模型、某类风险
```

现在很多 LLM 应用都会强调 **Prompt 版本管理、评测集、回归测试、监控**，原因就是所谓“更好的 Prompt”可能只是在某些样本上变好，在另一些样本上变差。已有研究也指出，通用“改进版 Prompt”可能带来能力取舍，所以要用评测驱动迭代，而不是凭感觉直接上线。

所以你的设计里最好不要叫“误判后自动改 Prompt”，而是叫：

> **反馈进入改进池，经过分析、验证、灰度后生效。**

------

## 二、建议的能力架构

可以把这个功能拆成 5 层。

```
1. 用户反馈层
2. 反馈治理层
3. 项目知识层
4. Review 生成增强层
5. 效果评估层
```

### 1. 用户反馈层：让用户能快速标记风险点

每条风险卡片下面可以有几个操作：

```
有用 / 无用 / 不准确 / 已忽略 / 已修复 / 不是本项目问题
```

对于“误判”不要只让用户写自由文本，最好提供结构化选项：

```
误判原因：
- 当前项目允许这种写法
- 已有外部逻辑兜底
- 该接口不会被外部调用
- 配置/表结构已在其他分支处理
- 风险级别过高
- 描述不准确
- 重复提醒
- 其他
```

然后再让用户补充一句说明。

这样做的好处是：
 **结构化字段用于统计和规则沉淀，自由文本用于补充上下文。**

------

### 2. 反馈治理层：不是所有反馈都应立即生效

你提到“用户填写的理由可能不清晰”，这很现实。

所以反馈要有状态流转：

```
待分析 → 有效反馈 → 待沉淀 → 已沉淀 → 已生效
      ↘ 无效反馈 / 信息不足 / 仅个例
```

可以用 AI 做一次“反馈质量分析”，但不要完全自动相信它。

反馈质量可以分几类：

| 类型       | 含义                           | 处理方式         |
| ---------- | ------------------------------ | ---------------- |
| 明确有效   | 用户说明清楚，能解释为什么误判 | 可进入项目知识库 |
| 信息不足   | 只写“没问题”“不用管”           | 暂不生效，只统计 |
| 个例反馈   | 只适用于当前 MR                | 不沉淀为规则     |
| 规则冲突   | 和安全/性能硬规则冲突          | 需要管理员确认   |
| 高价值反馈 | 多次出现、多人确认             | 优先改进         |

你可以设计一个“反馈置信度”：

```
feedback_confidence = 用户角色权重 + 重复次数 + 理由清晰度 + 是否被 reviewer 采纳
```

例如：

```
普通开发标记一次：只进入统计
项目负责人确认一次：进入项目规则候选
同类风险被 3 次以上标记误判：进入待优化池
```

------

### 3. 项目知识层：不要只改 Prompt，要沉淀项目组知识

你第 2 点说得很对：有些业务问题，AI 只看 changed files 判断不了。

这类问题不要强行靠 Prompt 解决，而是靠 **项目上下文增强**。

现在 AI Code Review 方向里，RAG 是常见做法：通过检索历史 PR/MR、历史 Review、项目规范、相似代码、架构文档来减少误判，让输出更贴合项目上下文。Graphite 对 AI code review 的说明里也提到，用过去的 PR 进行 RAG 可以帮助工具理解代码库特有模式，从而减少 false positives；相关研究也在探索用检索增强方式生成更贴近上下文的代码审查意见。

你的平台可以沉淀几类知识：

```
项目规范：
- 命名规范
- 接口规范
- 缓存规范
- MQ 规范
- 表结构变更规范
- 异常处理规范

项目事实：
- 哪些表是历史遗留表
- 哪些接口只内部调用
- 哪些字段允许为空
- 哪些缓存 key 有统一封装
- 哪些 MQ 消息允许最终一致

历史反馈：
- 哪些风险类型经常被标记误判
- 哪些代码模式在本项目中是允许的
- 哪些风险被确认是真问题
```

这就不是单纯 Prompt 了，而是：

```
Prompt + 项目知识库 + 风险规则 + 历史反馈 + 相似案例
```

------

## 三、针对你提出的 5 个问题逐个回答

## 1. 不同模型风险点不同，改 Prompt 会不会影响高准确率模型？

会。

所以建议你采用：

```
全局基础 Prompt
+ 模型专属适配 Prompt
+ 项目组 Prompt Patch
+ 风险类型 Prompt Patch
```

例如：

```
global_prompt_version = v1.0
model_adapter = deepseek-v3-adapter
project_policy = project-A-policy-v3
risk_type_policy = db-change-risk-v2
```

不要所有模型共用一份完全一样的最终 Prompt。

可以设计成：

```
最终 Prompt = 平台基础规则 + 模型适配规则 + 项目组规则 + 本次 MR 上下文
```

这样你就能做到：

| 场景                 | 修改位置       |
| -------------------- | -------------- |
| 所有模型都误判       | 改全局规则     |
| 只有某个模型误判     | 改模型适配层   |
| 只有某项目组觉得无用 | 改项目规则     |
| 只有 DB 风险误判多   | 改 DB 风险规则 |
| 只是某一次 MR 特例   | 不沉淀，只记录 |

这点非常重要。

------

## 2. 业务问题 AI 只靠 changed files 判断不了，怎么优化？

不要让 AI “硬猜”。

风险卡片应该允许输出一种状态：

```
需要更多上下文确认
```

例如：

```
风险：新增字段 user_status 未看到默认值处理
判断依据：当前 MR 只看到实体和 SQL 变更，未看到历史数据迁移脚本
需要确认：历史数据是否允许为空，是否有补偿脚本
```

也就是说，AI Review 不一定每次都要给“确定有问题”，可以分为：

```
确定风险
疑似风险
需要人工确认
仅建议
```

对于业务上下文，可以增强几类数据源：

```
1. MR diff
2. 当前文件上下文
3. 被调用方法上下文
4. 相关接口定义
5. 数据库表结构
6. 历史 MR / 历史 Review
7. 项目规范文档
8. Nacos 配置 / MQ topic / Redis key 规范
9. 线上调用链或接口清单
```

你的 MVP 可以先做简单版：

```
当用户标记“已有外部逻辑兜底 / 项目允许 / 业务特例”时，
系统自动生成一条“项目事实候选知识”。
```

例如：

```
项目事实：
在 ljdw-web 项目中，xxxService.saveDevice() 方法已经统一做设备权限校验，
因此调用方未重复校验不应直接判定为权限缺失。
```

以后遇到类似代码，就把这条知识检索出来喂给模型。

------

## 3. 用户标记后，什么时候改进？理由是否要筛选？

建议不要实时改进，至少分 3 档。

### A. 实时生效：仅对当前风险卡片

用户点“误判”后，当前 MR 的这条风险卡片状态变成：

```
已标记误判
```

不会影响后续 Review。

### B. 准实时生效：项目内相似风险降权

如果同类风险多次被标记误判，可以先不删除，而是降权：

```
高风险 → 中风险
中风险 → 低风险
低风险 → 仅提示
```

### C. 周期性生效：进入规则/知识库

建议按周期做：

```
每天/每周生成反馈分析报告
项目管理员确认后生效
```

例如：

```
本周项目 A 共 42 条风险被标记误判：
- DB 字段默认值类：12 条
- Redis key 命名类：9 条
- MQ 消费幂等类：6 条
建议新增 3 条项目规则，调整 2 条风险等级。
```

用户理由必须筛选。你可以做一个“反馈理由质量评分”：

```
0 分：空、无意义，例如“不用管”“没问题”
1 分：有态度但无依据，例如“这个不会出问题”
2 分：有业务解释，例如“该接口只内部调用”
3 分：有明确证据，例如“权限校验在 xxxFilter 已统一处理”
4 分：可沉淀为规则，例如“本项目所有 xxx 类型接口均由网关统一鉴权”
```

只有 3 分以上才建议进入“规则候选”。

------

## 4. 改进方式是不是只能改初始 Prompt？

不是。Prompt 只是最浅层的一种方式。

更好的改进方式至少有 8 种：

| 改进方式       | 适合场景                           |
| -------------- | ---------------------------------- |
| Prompt 调整    | 输出格式、判断标准、风险描述不稳定 |
| 项目知识库 RAG | 业务上下文、团队规范、历史特例     |
| 规则引擎调整   | 明确可编码的判断条件               |
| 风险等级策略   | 风险不是错，但等级过高             |
| 相似案例检索   | 历史上类似代码如何处理             |
| 模型路由       | 不同风险类型交给不同模型           |
| 二阶段 Review  | 先发现风险，再让另一个模型复核     |
| 评测集回归     | 防止改了 A 损坏 B                  |

你现在的平台已经有“规则引擎 + 风险卡片 + 变更分析”的基础，所以最适合走这条路线：

```
误判反馈
  ↓
归类为：规则问题 / 上下文不足 / 等级过高 / 描述问题 / 模型问题
  ↓
分别进入：规则库 / 项目知识库 / 等级策略 / Prompt Patch / 模型适配
```

不要只盯着 Prompt。

尤其是你要做“贴合每个项目组规范和习惯”，最应该强化的是：

```
项目组规则库 + 历史反馈知识库 + 评测集
```

------

## 5. 前端页面怎么展示？是否做成系统级能力？

建议做成系统级能力，但按权限和项目隔离。

前端可以分 3 个入口。

------

### 入口一：风险卡片上的轻量反馈

这是用户最常用的地方。

每张风险卡片底部：

```
[有用] [误判] [风险等级过高] [重复提醒] [已修复]
```

点“误判”后弹窗：

```
误判原因：
○ 项目允许这种写法
○ 已有外部逻辑兜底
○ 当前风险等级过高
○ AI 没有看到相关上下文
○ 规则不适用于本项目
○ 其他

补充说明：
[请输入原因，建议说明依据，例如在哪个类/配置/文档中已有处理]

是否作为项目经验沉淀？
□ 建议沉淀为项目规则
```

------

### 入口二：项目反馈池

给项目负责人或平台管理员看。

页面名称可以叫：

```
Review 反馈池
```

列表字段：

| 字段        | 含义                       |
| ----------- | -------------------------- |
| 项目        | 哪个项目                   |
| MR          | 来源 MR                    |
| 风险类型    | API/DB/CACHE/MQ/CONFIG     |
| 风险标题    | 原始风险点                 |
| 用户反馈    | 误判/等级过高/重复         |
| 反馈原因    | 用户选择 + 文本            |
| AI 分析结果 | 是否有沉淀价值             |
| 出现次数    | 同类问题次数               |
| 状态        | 待分析/待确认/已沉淀/忽略  |
| 操作        | 沉淀为规则/加入知识库/忽略 |

------

### 入口三：项目 Review 策略配置

页面名称可以叫：

```
项目 Review 策略
```

里面放：

```
1. 项目规则
2. 忽略规则
3. 风险等级策略
4. 历史反馈学习
5. Prompt 版本
6. 模型策略
7. 效果指标
```

例如：

```
项目规则：
- 本项目 Controller 层允许不写 try-catch，由全局异常处理器处理
- 本项目 Redis key 统一由 CacheKeyBuilder 生成，调用处不重复校验格式
- 本项目内部接口由网关统一鉴权，业务方法未出现鉴权代码不直接判定为权限风险
```

------

## 四、推荐的数据模型

你可以先设计这几张表。

### 1. 风险反馈表：risk_feedback

```
CREATE TABLE risk_feedback (
  id BIGINT PRIMARY KEY,
  project_id BIGINT NOT NULL,
  mr_id BIGINT NOT NULL,
  risk_card_id BIGINT NOT NULL,
  risk_type VARCHAR(64) NOT NULL,
  risk_title VARCHAR(255) NOT NULL,
  feedback_type VARCHAR(64) NOT NULL COMMENT 'USEFUL/FALSE_POSITIVE/LEVEL_TOO_HIGH/DUPLICATE/FIXED',
  reason_type VARCHAR(64) DEFAULT NULL COMMENT 'PROJECT_ALLOWED/HAS_EXTERNAL_GUARD/CONTEXT_MISSING/LEVEL_TOO_HIGH/OTHER',
  reason_text TEXT,
  user_id BIGINT NOT NULL,
  user_role VARCHAR(64) DEFAULT NULL,
  status VARCHAR(64) NOT NULL DEFAULT 'PENDING',
  quality_score INT DEFAULT NULL,
  created_at DATETIME NOT NULL,
  updated_at DATETIME NOT NULL
);
```

### 2. 项目知识候选表：project_knowledge_candidate

```
CREATE TABLE project_knowledge_candidate (
  id BIGINT PRIMARY KEY,
  project_id BIGINT NOT NULL,
  source_feedback_id BIGINT NOT NULL,
  knowledge_type VARCHAR(64) NOT NULL COMMENT 'RULE/FACT/EXCEPTION/CONVENTION',
  title VARCHAR(255) NOT NULL,
  content TEXT NOT NULL,
  confidence_score DECIMAL(5,2) DEFAULT NULL,
  status VARCHAR(64) NOT NULL DEFAULT 'PENDING',
  reviewer_id BIGINT DEFAULT NULL,
  created_at DATETIME NOT NULL,
  updated_at DATETIME NOT NULL
);
```

### 3. 项目 Review 规则表：project_review_policy

```
CREATE TABLE project_review_policy (
  id BIGINT PRIMARY KEY,
  project_id BIGINT NOT NULL,
  policy_type VARCHAR(64) NOT NULL COMMENT 'IGNORE_RULE/RISK_LEVEL/PROMPT_PATCH/KNOWLEDGE',
  risk_type VARCHAR(64) DEFAULT NULL,
  title VARCHAR(255) NOT NULL,
  content TEXT NOT NULL,
  enabled TINYINT NOT NULL DEFAULT 1,
  version INT NOT NULL DEFAULT 1,
  created_by BIGINT NOT NULL,
  created_at DATETIME NOT NULL,
  updated_at DATETIME NOT NULL
);
```

### 4. Review 效果评测样本表：review_eval_case

```
CREATE TABLE review_eval_case (
  id BIGINT PRIMARY KEY,
  project_id BIGINT NOT NULL,
  source_mr_id BIGINT DEFAULT NULL,
  source_risk_card_id BIGINT DEFAULT NULL,
  change_summary TEXT,
  diff_snapshot LONGTEXT,
  expected_result VARCHAR(64) NOT NULL COMMENT 'SHOULD_REPORT/SHOULD_NOT_REPORT/LOWER_LEVEL',
  expected_reason TEXT,
  risk_type VARCHAR(64),
  model_name VARCHAR(128),
  prompt_version VARCHAR(64),
  created_at DATETIME NOT NULL
);
```

这张表很关键。它可以帮助你避免：

> 改了一个 Prompt，解决了 5 个误判，却新增了 20 个漏判。

------

## 五、推荐的处理流程

可以设计成这样：

```
开发者看到风险卡片
  ↓
点击“误判”
  ↓
选择误判原因 + 填写说明
  ↓
系统记录反馈
  ↓
AI 对反馈进行质量分析
  ↓
如果质量高，生成“项目知识候选”
  ↓
项目管理员确认
  ↓
沉淀为项目规则 / 项目知识 / 忽略规则 / 风险等级策略
  ↓
后续 Review 时检索并应用
  ↓
定期统计误判率、采纳率、风险命中率
```

你可以把它理解成：

```
用户不是在“训练模型”，而是在“训练平台的项目上下文和规则系统”。
```

这个表述也更适合汇报。

------

## 六、MVP 阶段怎么做，不要一开始做太重

建议你分 3 个版本。

### V1：先做标记和统计

目标：让用户能反馈，平台能看见问题。

功能：

```
1. 风险卡片支持：有用 / 误判 / 等级过高 / 重复提醒
2. 误判原因结构化选择
3. 反馈记录入库
4. 项目维度统计误判率
5. 风险类型维度统计误判率
```

先不要自动改 Prompt。

------

### V2：做项目反馈池和规则候选

目标：让反馈能沉淀。

功能：

```
1. 反馈池页面
2. AI 分析反馈理由质量
3. 自动生成项目知识候选
4. 项目管理员确认后生效
5. 后续 Review 时把项目规则加入上下文
```

------

### V3：做评测闭环和模型策略

目标：让平台真的越用越准。

功能：

```
1. 从误判反馈生成评测样本
2. Prompt 版本管理
3. 模型维度效果对比
4. 项目维度策略灰度
5. 改进前后误判率对比
```

------

## 七、一个更成熟的最终形态

最终你可以把这块命名为：

> **Review Learning Center / Review 反馈学习中心**

里面有几个模块：

```
1. 风险反馈池
2. 项目规则库
3. 历史误判库
4. 高价值反馈
5. 模型效果对比
6. Prompt / 策略版本
7. Review 效果报表
```

核心指标：

```
误判率 = 被标记误判的风险数 / 总风险数
采纳率 = 被确认有用或已修复的风险数 / 总风险数
重复提醒率 = 被标记重复的风险数 / 总风险数
有效反馈率 = 高质量反馈数 / 总反馈数
策略命中率 = 项目规则参与判断的风险数 / 总风险数
```

这些指标能帮助你证明平台在进步。

------

## 八、我建议你的最终产品定位

这块功能不要叫：

```
误判标记
```

这个名字太小。

可以叫：

```
Review 反馈学习
项目 Review 经验沉淀
风险反馈闭环
项目规则学习
```

对外描述可以是：

> 平台支持对 AI Review 风险点进行反馈标记，并将高质量反馈沉淀为项目级 Review 规则、历史经验和评测样本。后续 Review 会结合项目规范、历史误判、相似案例和模型表现进行判断，从而减少重复误报，提升风险识别结果对不同项目组开发习惯的适配度。

------

## 九、我最推荐你当前落地的方案

结合你现在的 AI Review MVP，我建议下一步按这个优先级做：

```
P1：风险卡片增加反馈按钮
P2：risk_feedback 表入库
P3：反馈池页面
P4：反馈原因结构化
P5：AI 自动分析反馈质量
P6：项目知识候选生成
P7：项目管理员确认后，加入 Review 上下文
P8：建立 eval case，做 Prompt/模型回归评测
```

当前不要急着自动改 Prompt，也不要急着做模型微调。

你真正应该优先建设的是：

```
风险反馈数据资产
+ 项目规则沉淀机制
+ Review 策略版本管理
```

这三块做好后，后续无论接 DeepSeek、GPT、Claude、Gemini，还是本地模型，都能复用。