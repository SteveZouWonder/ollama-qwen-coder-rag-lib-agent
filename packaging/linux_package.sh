#!/usr/bin/env bash
# Linux 打包脚本 —— 将 PyInstaller onedir 产物封装为 AppImage。
#
# 用法（项目根目录执行，需先完成 pyinstaller 构建）：
#   APP_VERSION=1.0.0 packaging/linux_package.sh
#
# 依赖：appimagetool（脚本会自动下载）。
set -euo pipefail

APP_VERSION="${APP_VERSION:-0.0.0}"
APP_NAME="Cerebro"
DIST_DIR="dist"
SRC_DIR="${DIST_DIR}/${APP_NAME}"          # PyInstaller onedir 输出
APPDIR="${DIST_DIR}/${APP_NAME}.AppDir"
OUT="${DIST_DIR}/${APP_NAME}-${APP_VERSION}-x86_64.AppImage"

echo "==> 校验 PyInstaller 产物"
if [[ ! -d "${SRC_DIR}" ]]; then
  echo "错误：未找到 ${SRC_DIR}，请先运行 pyinstaller packaging/cerebro.spec --noconfirm"
  exit 1
fi

echo "==> 构建 AppDir 结构"
rm -rf "${APPDIR}"
mkdir -p "${APPDIR}/usr/bin"
mkdir -p "${APPDIR}/usr/share/applications"
mkdir -p "${APPDIR}/usr/share/icons/hicolor/256x256/apps"

# 拷贝程序本体
cp -R "${SRC_DIR}/." "${APPDIR}/usr/bin/"

# 图标
cp "assets/icon_256.png" "${APPDIR}/usr/share/icons/hicolor/256x256/apps/cerebro.png"
cp "assets/icon_256.png" "${APPDIR}/cerebro.png"

# .desktop 文件
cat > "${APPDIR}/cerebro.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=Cerebro
Comment=本地 RAG + 代码助手 (基于 Ollama)
Exec=Cerebro
Icon=cerebro
Categories=Utility;Development;
Terminal=false
EOF
cp "${APPDIR}/cerebro.desktop" "${APPDIR}/usr/share/applications/cerebro.desktop"

# AppRun 入口
cat > "${APPDIR}/AppRun" <<'EOF'
#!/bin/bash
HERE="$(dirname "$(readlink -f "${0}")")"
exec "${HERE}/usr/bin/Cerebro" "$@"
EOF
chmod +x "${APPDIR}/AppRun"

echo "==> 获取 appimagetool"
TOOL="appimagetool-x86_64.AppImage"
if [[ ! -x "${TOOL}" ]]; then
  wget -q "https://github.com/AppImage/AppImageKit/releases/download/continuous/${TOOL}" -O "${TOOL}"
  chmod +x "${TOOL}"
fi

echo "==> 生成 AppImage"
# CI 容器中通常无 FUSE，使用 --appimage-extract-and-run
ARCH=x86_64 ./"${TOOL}" --appimage-extract-and-run "${APPDIR}" "${OUT}"

echo "==> 完成：${OUT}"
