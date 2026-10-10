#!/bin/bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$PROJECT_DIR"
RUNTIME_DIR="$PROJECT_DIR/.runtime"
UV_VERSION="0.12.11"
UV="$RUNTIME_DIR/uv"

fail() {
    echo "$1" >&2
    if [[ -t 0 ]]; then read -r -p "按回车退出。" _; fi
    exit 1
}
trap 'fail "安装未完成。请检查网络，然后重新运行安装或启动脚本。"' ERR

[[ "$(uname -s)" == Darwin ]] || fail "此安装入口仅用于 macOS。其他系统请按 README 安装。"
case "$(uname -m)" in
    arm64) UV_TARGET="aarch64-apple-darwin" ;;
    x86_64) UV_TARGET="x86_64-apple-darwin" ;;
    *) fail "不支持当前 Mac 的处理器架构。" ;;
esac
mkdir -p "$RUNTIME_DIR"
export UV_CACHE_DIR="$RUNTIME_DIR/cache"
export UV_PYTHON_INSTALL_DIR="$RUNTIME_DIR/python"
export UV_PYTHON_BIN_DIR="$RUNTIME_DIR/bin"
export UV_PROJECT_ENVIRONMENT="$PROJECT_DIR/.venv"
export UV_LINK_MODE=copy

echo "首次安装需要联网。Python 与运行依赖会放在当前文件夹内。"
if [[ ! -x "$UV" ]]; then
    DOWNLOAD_DIR="$(mktemp -d "$RUNTIME_DIR/download.XXXXXX")"
    trap 'rm -rf "$DOWNLOAD_DIR"' EXIT
    ARCHIVE="uv-$UV_TARGET.tar.gz"
    BASE_URL="https://github.com/astral-sh/uv/releases/download/$UV_VERSION"
    echo "正在下载 Mac 安装工具…"
    curl --fail --location --retry 2 --connect-timeout 15 --max-time 180 \
        "$BASE_URL/$ARCHIVE" --output "$DOWNLOAD_DIR/$ARCHIVE"
    curl --fail --location --retry 2 --connect-timeout 15 --max-time 60 \
        "$BASE_URL/$ARCHIVE.sha256" --output "$DOWNLOAD_DIR/$ARCHIVE.sha256"
    (cd "$DOWNLOAD_DIR" && shasum -a 256 -c "$ARCHIVE.sha256")
    tar -xzf "$DOWNLOAD_DIR/$ARCHIVE" -C "$DOWNLOAD_DIR" "uv-$UV_TARGET/uv"
    mv "$DOWNLOAD_DIR/uv-$UV_TARGET/uv" "$UV"
    chmod +x "$UV"
fi

echo "正在准备 Python 3.11 与固定版本的运行依赖…"
"$UV" sync --frozen --no-dev --no-config --python 3.11 --managed-python
"$PROJECT_DIR/.venv/bin/python" -c 'import ios_location_controller, pymobiledevice3'
echo "安装完成。双击“启动 Route Studio.command”即可使用。"
