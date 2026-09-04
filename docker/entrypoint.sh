#!/bin/sh
# Container entrypoint.
#
# Config resolution order:
#   1. $GVT_CONFIG_YAML  -> written to $GVT_CONFIG (handy for Portainer stack env vars)
#   2. existing file at $GVT_CONFIG (bind mount / volume)
#   3. bundled config.example.yaml copied to $GVT_CONFIG on first start
set -eu

CONFIG_PATH="${GVT_CONFIG:-/config/config.yaml}"
mkdir -p "$(dirname "$CONFIG_PATH")" "$(dirname "${GVT_STATE_FILE:-/data/state.json}")"

if [ -n "${GVT_CONFIG_YAML:-}" ]; then
    printf '%s\n' "$GVT_CONFIG_YAML" > "$CONFIG_PATH"
    echo "entrypoint: wrote config from \$GVT_CONFIG_YAML to $CONFIG_PATH"
elif [ ! -f "$CONFIG_PATH" ]; then
    cp /app/config.example.yaml "$CONFIG_PATH"
    echo "entrypoint: no config found, seeded $CONFIG_PATH from config.example.yaml"
fi

exec python -m gvt_checker "$@"
