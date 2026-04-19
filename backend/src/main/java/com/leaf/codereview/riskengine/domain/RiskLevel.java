package com.leaf.codereview.riskengine.domain;

public enum RiskLevel {
    LOW(1),
    MEDIUM(2),
    HIGH(3),
    CRITICAL(4);

    private final int weight;

    RiskLevel(int weight) {
        this.weight = weight;
    }

    public int weight() {
        return weight;
    }

    public boolean higherThan(RiskLevel other) {
        return other == null || weight > other.weight;
    }
}