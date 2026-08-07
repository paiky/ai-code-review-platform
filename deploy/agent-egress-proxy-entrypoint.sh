#!/bin/sh
set -eu

config_path="/tmp/agent-egress-squid.conf"

cat >"$config_path" <<'EOF'
http_port 3128
pid_filename none

acl CONNECT method CONNECT
acl SSL_ports port 443
http_access allow CONNECT SSL_ports
http_access deny all

access_log none
cache_log /dev/null
cache_store_log none
cache deny all
forwarded_for delete
EOF

exec squid -N -f "$config_path"
