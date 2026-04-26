package com.leaf.codereview.notification;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.leaf.codereview.changeanalysis.domain.ChangeType;
import com.leaf.codereview.notification.application.DingTalkNotifier;
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
        assertThat(result.errorMessage()).isEqualTo("No focused risk item matched");
    }

    @Test
    void formatsOnlyFocusedRiskItemsBeforeSending() {
        RiskCard riskCard = riskCard(
                riskItem("DB_SCHEMA_CHANGE_CHECK", ChangeType.DB_SCHEMA, RiskLevel.HIGH),
                riskItem("CACHE_INVALIDATION_CHANGE_CHECK", ChangeType.CACHE_INVALIDATION, RiskLevel.HIGH)
        );

        DingTalkNotificationResult result = notifier.sendRiskCard(
                11L,
                riskCard,
                List.of("DB_SCHEMA")
        );

        assertThat(result.status()).isEqualTo(NotificationStatus.SKIPPED);
        assertThat(result.target()).isEqualTo("DINGTALK_WEBHOOK_URL");
        assertThat(result.requestDigest()).contains("[DB_SCHEMA]");
        assertThat(result.requestDigest()).contains("DB schema changed");
        assertThat(result.requestDigest()).doesNotContain("CACHE_INVALIDATION");
        assertThat(result.requestDigest()).doesNotContain("Cache invalidation changed");
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
        String title = category == ChangeType.DB_SCHEMA ? "DB schema changed" : "Cache invalidation changed";
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
