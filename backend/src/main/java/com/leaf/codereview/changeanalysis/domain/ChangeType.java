package com.leaf.codereview.changeanalysis.domain;

public enum ChangeType {
    API,
    DB,
    DB_SCHEMA,
    DB_SQL,
    ORM_MAPPING,
    ENTITY_MODEL,
    DATA_MIGRATION,
    CACHE,
    CACHE_KEY,
    CACHE_TTL,
    CACHE_INVALIDATION,
    CACHE_READ_WRITE,
    CACHE_SERIALIZATION,
    MQ,
    MQ_PRODUCER,
    MQ_CONSUMER,
    MQ_MESSAGE_SCHEMA,
    MQ_TOPIC_CONFIG,
    MQ_RETRY_DLQ,
    CONFIG;

    public boolean isDbFamily() {
        return this == DB
                || this == DB_SCHEMA
                || this == DB_SQL
                || this == ORM_MAPPING
                || this == ENTITY_MODEL
                || this == DATA_MIGRATION;
    }

    public boolean isCacheFamily() {
        return this == CACHE
                || this == CACHE_KEY
                || this == CACHE_TTL
                || this == CACHE_INVALIDATION
                || this == CACHE_READ_WRITE
                || this == CACHE_SERIALIZATION;
    }

    public boolean isMqFamily() {
        return this == MQ
                || this == MQ_PRODUCER
                || this == MQ_CONSUMER
                || this == MQ_MESSAGE_SCHEMA
                || this == MQ_TOPIC_CONFIG
                || this == MQ_RETRY_DLQ;
    }

    public ChangeType aggregateType() {
        if (isDbFamily()) {
            return DB;
        }
        if (isCacheFamily()) {
            return CACHE;
        }
        if (isMqFamily()) {
            return MQ;
        }
        return this;
    }
}
