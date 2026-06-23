#!/usr/bin/env bash
# macOS 打包脚本 —— 对 PyInstaller 产出的 .app 做 ad-hoc 签名并封装为 .dmg。
#
# 用法（项目根目录执行，需先完成 pyinstaller 构建）：
#   APP_VERSION=1.0.0 packaging/macos_package.sh
#
# 依赖：
#   - codesign（系统自带）
#   - create-dmg（brew install create-dmg）
#
# 说明：本项目为免费开源项目，未购买 Apple 开发者证书，
#       采用 ad-hoc 签名（codesign --sign -），可减少部分"已损坏"报错，
#       但用户首次打开仍需"右键 -> 打开"。
set -euo pipefail

APP_VERSION="${APP_VERSION:-0.0.0}"
APP_NAME="Cerebro"
DIST_DIR="dist"
APP_PATH="${DIST_DIR}/${APP_NAME}.app"
DMG_DIR="${DIST_DIR}/dmg"
DMG_PATH="${DIST_DIR}/${APP_NAME}-${APP_VERSION}.dmg"
ENTITLEMENTS="packaging/entitlements.plist"

echo "==> 校验 .app 是否存在"
if [[ ! -d "${APP_PATH}" ]]; then
  echo "错误：未找到 ${APP_PATH}，请先运行 pyinstaller packaging/cerebro.spec --noconfirm"
  exit 1
fi

echo "==> 对 .app 进行 ad-hoc 签名（深度、含 entitlements）"
# --deep 对内部所有可执行/动态库一并签名；ad-hoc 身份用 "-"
codesign --force --deep --sign - \
  --entitlements "${ENTITLEMENTS}" \
  --options runtime \
  "${APP_PATH}" || {
    # 部分环境 --options runtime 会因 ad-hoc 失败，退回不带 hardened runtime
    echo "==> 带 hardened runtime 签名失败，回退为基础 ad-hoc 签名"
    codesign --force --deep --sign - "${APP_PATH}"
  }

echo "==> 验证签名"
codesign --verify --verbose "${APP_PATH}" || echo "（ad-hoc 签名验证警告可忽略）"

echo "==> 准备 DMG 内容目录"
rm -rf "${DMG_DIR}"
mkdir -p "${DMG_DIR}"
cp -R "${APP_PATH}" "${DMG_DIR}/"

# 首次打开说明（中英）
cat > "${DMG_DIR}/首次打开请先读我.txt" <<'EOF'
Cerebro —— 首次打开说明
================================

本应用为免费开源项目，未购买 Apple 开发者证书，因此未做苹果公证。
macOS 首次打开时可能提示"无法验证开发者"或"已损坏"，这属于正常现象。

请按以下步骤打开（任选其一）：

方式一（推荐）：
  1. 将 Cerebro.app 拖入"应用程序"文件夹。
  2. 在"应用程序"中【右键点击】Cerebro -> 选择"打开"。
  3. 在弹窗中再次点击"打开"。之后即可正常双击启动。

方式二（若提示"已损坏，无法打开"）：
  打开"终端"，执行：
    xattr -dr com.apple.quarantine /Applications/Cerebro.app
  然后正常双击打开。

注意：Cerebro 需要本地 Ollama 服务。首次启动会自动检测，
若未安装会引导你安装 Ollama 并拉取所需模型。

Open Source · No Apple Developer Certificate · Unsigned build
EOF

echo "==> 生成 DMG"
if command -v create-dmg >/dev/null 2>&1; then
  create-dmg \
    --volname "${APP_NAME} ${APP_VERSION}" \
    --window-pos 200 120 \
    --window-size 640 400 \
    --icon-size 100 \
    --icon "${APP_NAME}.app" 160 200 \
    --app-drop-link 480 200 \
    --no-internet-enable \
    "${DMG_PATH}" \
    "${DMG_DIR}" || {
      echo "==> create-dmg 失败，回退使用 hdiutil"
      hdiutil create -volname "${APP_NAME} ${APP_VERSION}" \
        -srcfolder "${DMG_DIR}" -ov -format UDZO "${DMG_PATH}"
    }
else
  echo "==> 未安装 create-dmg，使用 hdiutil 生成基础 DMG"
  hdiutil create -volname "${APP_NAME} ${APP_VERSION}" \
    -srcfolder "${DMG_DIR}" -ov -format UDZO "${DMG_PATH}"
fi

echo "==> 完成：${DMG_PATH}"
