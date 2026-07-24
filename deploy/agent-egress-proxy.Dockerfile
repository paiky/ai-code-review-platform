FROM debian:12-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates squid \
    && rm -rf /var/lib/apt/lists/* \
    && chown -R proxy:proxy /var/spool/squid /var/log/squid

COPY deploy/agent-egress-squid.conf /etc/squid/squid.conf

USER proxy:proxy
EXPOSE 3128
ENTRYPOINT ["squid", "-N", "-f", "/etc/squid/squid.conf"]
