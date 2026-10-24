# 临时新增项目专用 Prompt Profile

适用于现有 MySQL 数据库：保留项目真实端类型，复制已有 Profile 并追加项目要求，再通过项目配置选择。仅新增数据，不增加端类型、不执行数据库迁移。

2026-10-24 系统修复后，优先使用“设置 → AI Review 配置 → 策略与 Prompt → 复制为新 Profile”，再编辑并保存、到项目配置中选择。本 SQL 保留供尚未部署修复版本的环境临时使用；已有 SQL 导入项会自动出现在修复后的管理页面，无需再次插入。

核验记录（2026-10-23）：已连接目标 `ai_code_review` 库（MySQL 5.7.31），确认创建语句的 28 个字段、必填字段和 Profile 唯一索引匹配；来源 `backend-default-ai-review` 存在且启用。创建及回滚语句均通过目标库 `EXPLAIN`，创建语句的 SELECT 投影返回 1 条候选记录。核验仅使用 SET、元数据查询、SELECT 和 EXPLAIN，未执行 INSERT/UPDATE/DELETE，也未绑定项目。执行时仍需填写实际补充要求，并按下文验收。

排序规则补充核验：在同一目标库将连接和变量设为 `utf8mb4_general_ci`，旧版等值比较复现 1267；修正版在 general_ci 会话，以及改为 unicode_ci 会话但保留旧 general_ci 变量的两种情况下，创建语句 EXPLAIN、SELECT 投影、中文指令拼接、结果查询和回滚 EXPLAIN 均通过。未执行实际写入。

## 1. 创建前确认

在连接目标环境数据库的 MySQL 客户端中操作。先在项目配置中记录原 Profile 编码，供回滚使用；未显式配置时记录当前端类型的默认 Profile。

执行下面的只读查询，确认数据库和复制来源：

```sql
SELECT DATABASE() AS current_database;

SELECT profile_code, profile_name, enabled, status, provider_code, model
FROM code_quality_review_profiles
ORDER BY id;
```

## 2. 创建临时 Profile

打开同目录的 [temporary-review-profile.sql](temporary-review-profile.sql)，修改开头四个参数：

- `@source_profile_code`：已有的同技术端 Profile，例如 `backend-default-ai-review`。
- `@new_profile_code`：新的唯一编码，最多 64 个字符，不使用内置 Profile 编码。
- `@new_profile_name`：项目选择器显示名称，最多 128 个字符。
- `@extra_instructions`：项目补充要求，初始为 `NULL`，必须替换为实际文本；SQL 字符串中的单引号写为两个单引号。

在同一个 MySQL 会话中执行 SQL 文件。也可在 mysql 命令行客户端中使用：

```text
source D:/projects/ai-code-review-platform/docs/temporary-review-profile.sql
```

脚本复制原 Profile 的完整配置，将原 `review_instructions` 与补充要求组合，并同步写入三个指令字段。Provider 和模型覆盖沿用来源值。已有同编码记录时不覆盖；来源不存在、未启用、原指令为空或补充要求为空时不插入。

结果必须显示 `inserted_rows = 1`，并核对新记录的名称和完整指令。为 0 时不要继续绑定：检查参数和是否已存在同编码记录。普通客户端需按 UTF-8 读取文件；mysql 命令行客户端可使用 `--default-character-set=utf8mb4` 连接。

脚本保留 `SET NAMES utf8mb4 COLLATE utf8mb4_unicode_ci`，并在 Profile 编码比较、指令拼接时对变量显式执行 `CONVERT(... USING utf8mb4) COLLATE utf8mb4_unicode_ci`，避免已有变量仍采用 `utf8mb4_general_ci` 时发生冲突。`SET NAMES` 不会追溯修改已赋值变量的排序规则；客户端单独重跑语句或自动恢复连接设置时也不能只依赖它。新增指令与原指令组合后的 UTF-8 内容需小于等于 TEXT 的 65535 字节限制。

若旧脚本执行报 1267，先在报错的同一会话执行 `ROLLBACK;` 结束未完成事务，再使用更新版脚本并保留已填写的四个参数，从头执行。参数赋值与 SQL 仍必须位于同一个连接；不要只选中 INSERT 后直接在另一个连接执行。

## 3. 项目选择与验收

1. 重新打开项目配置抽屉，保留真实端类型，例如“后端”。
2. 在“AI Review Profile”中选择新名称，核对路径及其他配置后保存。
3. 新建一次手动 Review，在任务详情核对 `profileCode` 是否为新编码，再检查结果是否遵循补充要求。需验证自动触发时，再按该项目已开启的 MR/Push 链路验收。

项目保存会沿用现有页面行为：清理项目 Provider/模型覆盖，路径编辑器初始值使用端类型默认路径；有历史覆盖或自定义路径时，保存前需核对。尚未部署系统修复的旧版全局 Prompt 编辑页只展示四个固定内置项，自定义 Profile 的指令可通过现有 PUT 接口或数据库维护；修复版可以直接在全局页面编辑。

如需只读核对数据库绑定，在下列查询中填写平台项目 ID（不是 GitLab 项目 ID）：

```sql
SELECT p.id, p.name, p.target_type,
       p.default_code_quality_profile_code,
       c.code_quality_profile_code AS target_profile_code,
       c.enabled AS target_config_enabled
FROM projects AS p
LEFT JOIN project_target_configs AS c
  ON c.project_id = p.id AND c.target_type = p.target_type
WHERE p.id = 123; -- 替换为平台项目 ID
```

新增 Profile 不会改变已组装的在途 Agent 输入。验收使用新任务。

## 4. 回滚

先在所有使用该临时 Profile 的项目中选回各自记录的原 Profile，保存。然后在 MySQL 客户端执行以下 SQL；编码需与创建时一致：

```sql
SET NAMES utf8mb4 COLLATE utf8mb4_unicode_ci;
SET @temporary_profile_code = 'project-a-temp-ai-review';

-- 核对是否还有项目引用，包括未启用的端配置。
SELECT id, name, default_code_quality_profile_code
FROM projects
WHERE default_code_quality_profile_code = CONVERT(@temporary_profile_code USING utf8mb4) COLLATE utf8mb4_unicode_ci;

SELECT project_id, target_type, enabled
FROM project_target_configs
WHERE code_quality_profile_code = CONVERT(@temporary_profile_code USING utf8mb4) COLLATE utf8mb4_unicode_ci;

-- 两类项目绑定均已解除时才禁用，保留 Profile 和历史任务记录。
UPDATE code_quality_review_profiles AS profile
SET profile.enabled = FALSE, profile.updated_at = NOW(3)
WHERE profile.profile_code = CONVERT(@temporary_profile_code USING utf8mb4) COLLATE utf8mb4_unicode_ci
  AND NOT EXISTS (
    SELECT 1 FROM projects AS p
    WHERE p.default_code_quality_profile_code = CONVERT(@temporary_profile_code USING utf8mb4) COLLATE utf8mb4_unicode_ci
  )
  AND NOT EXISTS (
    SELECT 1 FROM project_target_configs AS c
    WHERE c.code_quality_profile_code = CONVERT(@temporary_profile_code USING utf8mb4) COLLATE utf8mb4_unicode_ci
  );

SELECT profile_code, enabled, status
FROM code_quality_review_profiles
WHERE profile_code = CONVERT(@temporary_profile_code USING utf8mb4) COLLATE utf8mb4_unicode_ci;
```

回滚前等使用该 Profile 的任务结束；禁用后自定义 Profile 从项目可选列表消失。回滚不删除历史 Review 结果。
