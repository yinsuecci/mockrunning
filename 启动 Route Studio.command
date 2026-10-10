#!/bin/bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$PROJECT_DIR"
PYTHON="$PROJECT_DIR/.venv/bin/python"
PORT="${ROUTE_STUDIO_PORT:-8765}"
URL="http://127.0.0.1:$PORT"

fail() {
    echo "$1" >&2
    if [[ -t 0 ]]; then read -r -p "按回车退出。" _; fi
    exit 1
}

if [[ ! -x "$PYTHON" ]] || ! "$PYTHON" -c 'import ios_location_controller, pymobiledevice3' >/dev/null 2>&1; then
    echo "首次运行，正在准备环境…"
    /bin/bash "$PROJECT_DIR/安装或修复 Route Studio.command" || fail "安装未完成，请查看上方错误信息。"
fi
[[ "$PORT" =~ ^[0-9]+$ ]] || fail "端口必须是整数。"
[[ "$PORT" -ge 1 && "$PORT" -le 65535 ]] || fail "端口必须在 1–65535 之间。"

check_health() {
    local response
    response="$(curl --noproxy '*' -fsS --max-time 1 "$URL/api/health" 2>/dev/null)" || return 1
    [[ "$response" == *'"app": "ios-location-controller"'* ]]
}

open_page() {
    if [[ "${ROUTE_STUDIO_OPEN_BROWSER:-1}" == 1 ]]; then
        open "$URL" || echo "请手动在浏览器打开：$URL"
    fi
}

if check_health; then
    echo "Route Studio 已在运行：$URL"
    open_page
    exit 0
fi
if lsof -nP -iTCP:"$PORT" -sTCP:LISTEN >/dev/null 2>&1; then
    fail "端口 $PORT 已被其他服务占用，请检查后再启动。"
fi

echo "正在启动 Route Studio：$URL"
echo "请保持这个终端窗口打开；正常结束请先在网页停止/断开手机，再按 Control+C。"

(
    for _ in {1..50}; do
        if check_health; then open_page; exit 0; fi
        sleep .2
    done
    echo "页面未自动打开，请查看终端错误信息。" >&2
) &

exec "$PYTHON" -m ios_location_controller map --port "$PORT"
