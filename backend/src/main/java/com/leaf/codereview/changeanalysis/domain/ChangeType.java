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
    MQ,
    CONFIG;

    public boolean isDbFamily() {
        return this == DB
                || this == DB_SCHEMA
                || this == DB_SQL
                || this == ORM_MAPPING
                || this == ENTITY_MODEL
                || this == DATA_MIGRATION;
    }
}
