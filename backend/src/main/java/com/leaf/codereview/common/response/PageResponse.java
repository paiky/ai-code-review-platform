package com.leaf.codereview.common.response;

import java.util.List;

public class PageResponse<T> {

    private final List<T> items;
    private final int pageNo;
    private final int pageSize;
    private final long total;

    public PageResponse(List<T> items, int pageNo, int pageSize, long total) {
        this.items = items;
        this.pageNo = pageNo;
        this.pageSize = pageSize;
        this.total = total;
    }

    public List<T> getItems() {
        return items;
    }

    public int getPageNo() {
        return pageNo;
    }

    public int getPageSize() {
        return pageSize;
    }

    public long getTotal() {
        return total;
    }
}
