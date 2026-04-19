package com.leaf.codereview.common.web;

import org.slf4j.MDC;

public final class TraceIdHolder {

    public static final String TRACE_ID_KEY = "traceId";

    private TraceIdHolder() {
    }

    public static String getTraceId() {
        return MDC.get(TRACE_ID_KEY);
    }
}
