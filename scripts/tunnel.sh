#!/bin/bash
# Cloudflare quick tunnel to localhost:8000. Retries until it works, then writes PUBLIC_BASE_URL to .env.
cd "$(dirname "$0")/.."
LOG=/tmp/tunnel.log
PID=""
trap 'kill $PID 2>/dev/null; exit' INT TERM
while true; do
  URL=""
  caffeinate -dims cloudflared tunnel --protocol http2 --url http://localhost:8000 > "$LOG" 2>&1 &
  PID=$!
  for i in $(seq 1 30); do
    URL=$(grep -o 'https://[a-z0-9-]*\.trycloudflare\.com' "$LOG" | grep -v '//api\.' | head -1)
    [ -n "$URL" ] && break
    kill -0 $PID 2>/dev/null || break
    sleep 1
  done
  if [ -n "$URL" ]; then
    sed -i '' "s|^PUBLIC_BASE_URL=.*|PUBLIC_BASE_URL=$URL|" .env
    echo ""
    echo "TUNNEL READY: $URL"
    echo "Now restart uvicorn in its tab."
    wait $PID
    echo "Tunnel stopped. Starting a new one, restart uvicorn again after READY."
  else
    kill $PID 2>/dev/null
    echo "Tunnel request failed, retrying in 5 s..."
    sleep 5
  fi
done
