FROM debian:12-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates squid \
    && rm -rf /var/lib/apt/lists/* \
    && chown -R proxy:proxy /var/spool/squid /var/log/squid

COPY deploy/agent-egress-squid.conf /etc/squid/squid.conf
COPY deploy/agent-egress-proxy-entrypoint.sh /usr/local/bin/agent-egress-proxy-entrypoint
RUN chmod 0755 /usr/local/bin/agent-egress-proxy-entrypoint

USER proxy:proxy
EXPOSE 3128
ENTRYPOINT ["/usr/local/bin/agent-egress-proxy-entrypoint"]
