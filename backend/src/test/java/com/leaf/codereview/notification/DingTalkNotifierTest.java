package com.leaf.codereview.notification;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.leaf.codereview.changeanalysis.domain.ChangeType;
import com.leaf.codereview.codequality.domain.CodeQualityFinding;
import com.leaf.codereview.codequality.domain.CodeQualityReviewProviderType;
import com.leaf.codereview.codequality.domain.CodeQualityReviewResult;
import com.leaf.codereview.codequality.infrastructure.CodeQualityReviewSettingsRepository;
import com.leaf.codereview.notification.application.DingTalkNotifier;
import com.leaf.codereview.notification.domain.DingTalkMessageContext;
import com.leaf.codereview.notification.domain.DingTalkNotificationResult;
import com.leaf.codereview.notification.domain.NotificationStatus;
import com.leaf.codereview.riskengine.domain.ReviewRole;
import com.leaf.codereview.riskengine.domain.RiskCard;
import com.leaf.codereview.riskengine.domain.RiskItem;
import com.leaf.codereview.riskengine.domain.RiskLevel;
import org.junit.jupiter.api.Test;

import java.time.OffsetDateTime;
import java.util.List;
import java.util.Set;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;

class DingTalkNotifierTest {

    private final DingTalkNotifier notifier = new DingTalkNotifier(new ObjectMapper(), "", true);

    @Test
    void skipsNotificationWhenFocusedRiskItemsAreMissing() {
        RiskCard riskCard = riskCard(
                riskItem("CACHE_INVALIDATION_CHANGE_CHECK", ChangeType.CACHE_INVALIDATION, RiskLevel.HIGH)
        );

        DingTalkNotificationResult result = notifier.sendRiskCard(
                10L,
                riskCard,
                List.of("DB_SCHEMA", "DATA_MIGRATION", "ENTITY_MODEL")
        );

        assertThat(result.status()).isEqualTo(NotificationStatus.SKIPPED);
        assertThat(result.target()).isEqualTo("DINGTALK_FOCUS_CHANGE_TYPES");
        assertThat(result.errorMessage()).isEqualTo("No focused reminder matched");
    }

    @Test
    void formatsOnlyFocusedRiskItemsBeforeSending() {
        RiskCard riskCard = riskCard(
                riskItem("DB_SCHEMA_CHANGE_CHECK", ChangeType.DB_SCHEMA, RiskLevel.HIGH),
                riskItem("DB_SQL_CHANGE_CHECK", ChangeType.DB_SQL, RiskLevel.MEDIUM),
                riskItem("CACHE_INVALIDATION_CHANGE_CHECK", ChangeType.CACHE_INVALIDATION, RiskLevel.HIGH)
        );

        DingTalkNotificationResult result = notifier.sendRiskCard(
                11L,
                riskCard,
                List.of("DB_SCHEMA", "DB_SQL")
        );

        assertThat(result.status()).isEqualTo(NotificationStatus.SKIPPED);
        assertThat(result.target()).isEqualTo("DINGTALK_WEBHOOK_URL");
        assertThat(result.requestDigest()).contains("作者");
        assertThat(result.requestDigest()).contains("### 变更提醒");
        assertThat(result.requestDigest()).contains("**提醒**");
        assertThat(result.requestDigest()).doesNotContain("维护事项提醒");
        assertThat(result.requestDigest()).doesNotContain("变更提醒 #11");
        assertThat(result.requestDigest()).contains("DB 变更提醒：命中 DB 表结构、SQL，共 2 条提醒");
        assertThat(result.requestDigest()).doesNotContain("触发提醒");
        assertThat(result.requestDigest()).doesNotContain("上线前请准备并核对 SQL");
        assertThat(result.requestDigest()).doesNotContain("DB schema changed");
        assertThat(result.requestDigest()).doesNotContain("高风险");
        assertThat(result.requestDigest()).doesNotContain("置信度");
        assertThat(result.requestDigest()).doesNotContain("CACHE_INVALIDATION");
        assertThat(result.requestDigest()).doesNotContain("Cache invalidation changed");
    }

    @Test
    void formatsAuthorAndPlatformDetailLink() {
        DingTalkNotifier notifierWithPlatformUrl = new DingTalkNotifier(new ObjectMapper(), "", "http://localhost:5173/", true);
        String markdown = notifierWithPlatformUrl.formatMarkdown(
                12L,
                riskCard(riskItem("DB_SCHEMA_CHANGE_CHECK", ChangeType.DB_SCHEMA, RiskLevel.HIGH)),
                new DingTalkMessageContext(
                        "GitLab MR !12 feature/order -> master",
                        "Alice",
                        "alice",
                        "feature/order",
                        "master",
                        "https://gitlab.example.com/group/demo/-/merge_requests/12"
                )
        );

        assertThat(markdown).contains("Alice(@alice)");
        assertThat(markdown).contains("feature/order -> master");
        assertThat(markdown).contains("[查看平台详情](http://localhost:5173/?taskId=12)");
        assertThat(markdown).doesNotContain("查看 GitLab");
        assertThat(markdown).doesNotContain("gitlab.example.com");
    }

    @Test
    void formatsCodeQualityReviewResult() {
        DingTalkNotifier notifierWithPlatformUrl = new DingTalkNotifier(new ObjectMapper(), "", "http://localhost:5173/", true);
        CodeQualityReviewResult reviewResult = CodeQualityReviewResult.success(
                CodeQualityReviewProviderType.OPENAI_API,
                "HIGH",
                "发现 1 个事务一致性问题。",
                List.of(new CodeQualityFinding(
                        "MAJOR",
                        "TRANSACTION",
                        "src/main/java/com/demo/OrderService.java",
                        42,
                        48,
                        "订单创建缺少事务边界",
                        "body",
                        "suggestion",
                        "HIGH",
                        "OPENAI_API"
                )),
                "{}",
                null,
                OffsetDateTime.now(),
                OffsetDateTime.now()
        );

        String markdown = notifierWithPlatformUrl.formatCodeQualityMarkdown(
                99L,
                reviewResult,
                new DingTalkMessageContext(
                        "GitLab MR !99 feature/order -> master",
                        "Alice",
                        "alice",
                        "feature/order",
                        "master",
                        null
                )
        );

        assertThat(markdown).contains("### 代码质量 Review");
        assertThat(markdown).contains("OPENAI_API");
        assertThat(markdown).contains("发现 1 个事务一致性问题");
        assertThat(markdown).contains("订单创建缺少事务边界");
        assertThat(markdown).contains("src/main/java/com/demo/OrderService.java:42");
        assertThat(markdown).contains("[查看平台详情](http://localhost:5173/?taskId=99)");
    }

    @Test
    void formatsCombinedReviewSummaryCompactly() {
        DingTalkNotifier notifierWithPlatformUrl = new DingTalkNotifier(new ObjectMapper(), "", "http://localhost:5173/", true);
        RiskCard riskCard = riskCard(
                riskItem("DB_SCHEMA_CHANGE_CHECK", ChangeType.DB_SCHEMA, RiskLevel.HIGH),
                riskItem("CACHE_READ_WRITE_CHANGE_CHECK", ChangeType.CACHE_READ_WRITE, RiskLevel.MEDIUM),
                riskItem("CONFIG_RELEASE_CHECK", ChangeType.CONFIG, RiskLevel.LOW)
        );
        CodeQualityReviewResult reviewResult = CodeQualityReviewResult.success(
                CodeQualityReviewProviderType.OPENAI_API,
                "HIGH",
                "long summary should not be included",
                List.of(
                        new CodeQualityFinding("CRITICAL", "CODE_QUALITY", "A.java", 1, 1, "代码可能存在空指针异常", "", "", "HIGH", "OPENAI_API"),
                        new CodeQualityFinding("MAJOR", "CODE_QUALITY", "B.java", 2, 2, "微信迁移清洗可能导致数据库与缓存不一致", "", "", "HIGH", "OPENAI_API"),
                        new CodeQualityFinding("MAJOR", "CODE_QUALITY", "C.java", 3, 3, "退款原因字段缺少校验，可能导致落库失败或脏数据", "", "", "HIGH", "OPENAI_API")
                ),
                "{}",
                null,
                OffsetDateTime.now(),
                OffsetDateTime.now()
        );

        String markdown = notifierWithPlatformUrl.formatReviewSummaryMarkdown(
                54L,
                riskCard,
                reviewResult,
                new DingTalkMessageContext(
                        "GitLab MR !373 feat/app-refund -> master",
                        "林沛",
                        "linpei",
                        "feat/app-refund",
                        "master",
                        null
                )
        );

        assertThat(markdown).contains("### 变更审查结果");
        assertThat(markdown).contains("MR !373 feat/app-refund -> master");
        assertThat(markdown).contains("作者：林沛(@linpei)");
        assertThat(markdown).contains("#### 维护提醒（规则扫描）");
        assertThat(markdown).contains("#### 代码质量 Review（AI）");
        assertThat(markdown).contains("数据库变更：请确认脚本是否需要准备");
        assertThat(markdown).contains("Redis 变更：请确认缓存 key 是否需要配置");
        assertThat(markdown).contains("配置变更：请确认是否有新的 Nacos 配置");
        assertThat(markdown).contains("**紧急需要修复：1 个**\n- 代码可能存在空指针异常。");
        assertThat(markdown).contains("**可能需要修复：2 个**");
        assertThat(markdown).contains("代码可能存在空指针异常。\n\n**可能需要修复：2 个**");
        assertThat(markdown).contains("代码可能存在空指针异常。");
        assertThat(markdown).contains("详情：http://localhost:5173/?taskId=54");
        assertThat(markdown).doesNotContain("状态");
        assertThat(markdown).doesNotContain("Provider");
        assertThat(markdown).doesNotContain("long summary should not be included");
        assertThat(markdown).doesNotContain("A.java");
    }

    @Test
    void skipsCombinedReviewSummaryWhenNoReminderOrCodeQualityFindingExists() {
        DingTalkNotifier notifierWithWebhook = new DingTalkNotifier(new ObjectMapper(), "https://example.com/webhook", "http://localhost:5173/", true);
        CodeQualityReviewResult reviewResult = CodeQualityReviewResult.success(
                CodeQualityReviewProviderType.OPENAI_API,
                "LOW",
                "未发现需要修复的问题。",
                List.of(),
                "{}",
                null,
                OffsetDateTime.now(),
                OffsetDateTime.now()
        );

        DingTalkNotificationResult result = notifierWithWebhook.sendReviewSummary(
                55L,
                riskCard(),
                List.of("DB_SCHEMA", "DATA_MIGRATION", "ENTITY_MODEL"),
                reviewResult,
                DingTalkMessageContext.empty()
        );

        assertThat(result.status()).isEqualTo(NotificationStatus.SKIPPED);
        assertThat(result.target()).isEqualTo("DINGTALK_REVIEW_SUMMARY");
        assertThat(result.errorMessage()).isEqualTo("No focused reminders or code quality findings matched");
    }

    @Test
    void skipsDingTalkWhenGlobalSwitchIsDisabled() {
        CodeQualityReviewSettingsRepository settingsRepository = mock(CodeQualityReviewSettingsRepository.class);
        when(settingsRepository.dingtalkNotificationEnabled()).thenReturn(false);
        DingTalkNotifier notifierWithGlobalSwitch = new DingTalkNotifier(
                new ObjectMapper(),
                "https://example.com/webhook",
                "http://localhost:5173/",
                true,
                settingsRepository
        );

        DingTalkNotificationResult result = notifierWithGlobalSwitch.sendRiskCard(
                56L,
                riskCard(riskItem("DB_SCHEMA_CHANGE_CHECK", ChangeType.DB_SCHEMA, RiskLevel.HIGH))
        );

        assertThat(result.status()).isEqualTo(NotificationStatus.SKIPPED);
        assertThat(result.target()).isEqualTo("DINGTALK_NOTIFICATION_ENABLED");
        assertThat(result.errorMessage()).isEqualTo("DingTalk notification is disabled");
    }

    private RiskCard riskCard(RiskItem... riskItems) {
        return new RiskCard(
                "risk-card-test",
                "summary",
                RiskLevel.HIGH,
                List.of(),
                List.of(riskItems),
                List.of("template check"),
                Set.of(ReviewRole.BACKEND),
                OffsetDateTime.parse("2026-04-21T22:38:00+08:00"),
                "test"
        );
    }

    private RiskItem riskItem(String ruleCode, ChangeType category, RiskLevel riskLevel) {
        String title = switch (category) {
            case DB_SCHEMA -> "DB schema changed";
            case DB_SQL -> "SQL changed";
            default -> "Cache invalidation changed";
        };
        return new RiskItem(
                ruleCode + "-001",
                ruleCode,
                category,
                riskLevel,
                title,
                "description",
                "impact",
                List.of(),
                List.of(),
                List.of(title + " check"),
                Set.of(ReviewRole.BACKEND),
                "HIGH",
                "reason",
                List.of()
        );
    }
}
