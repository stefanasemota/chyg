#!/usr/bin/env sh
# Optional convenience installer for chyg (Context Hygiene CLI).
set -eu

REPO_OWNER="${CHYG_REPO_OWNER:-stefanasemota}"
REPO_NAME="${CHYG_REPO_NAME:-chyg}"
BRANCH="${CHYG_BRANCH:-main}"
DOWNLOAD_URL="${CHYG_UPDATE_URL:-https://raw.githubusercontent.com/${REPO_OWNER}/${REPO_NAME}/${BRANCH}/chyg}"

if [ -n "${CHYG_INSTALL_DIR:-}" ]; then
  INSTALL_DIR="$CHYG_INSTALL_DIR"
elif [ -d "$HOME/.local/bin" ] || mkdir -p "$HOME/.local/bin" 2>/dev/null; then
  INSTALL_DIR="$HOME/.local/bin"
elif [ -w "/usr/local/bin" ]; then
  INSTALL_DIR="/usr/local/bin"
else
  echo "Error: Could not find a writable install directory (~/.local/bin or /usr/local/bin)." >&2
  exit 1
fi

TARGET="${INSTALL_DIR}/chyg"
TMP_FILE="${TARGET}.tmp.$$"

echo "Downloading chyg from ${DOWNLOAD_URL}..."
if ! curl -fsSL "$DOWNLOAD_URL" -o "$TMP_FILE"; then
  rm -f "$TMP_FILE"
  echo "Error: Failed to download chyg." >&2
  exit 1
fi

chmod +x "$TMP_FILE"
mv -f "$TMP_FILE" "$TARGET"
echo "Installed chyg to ${TARGET}"

case ":${PATH}:" in
  *":${INSTALL_DIR}:"*)
    echo "Verified: ${INSTALL_DIR} is in your PATH."
    ;;
  *)
    echo "Note: ${INSTALL_DIR} is not in your PATH."
    echo "Add it to your shell profile (~/.zshrc):"
    echo "  export PATH=\"${INSTALL_DIR}:\$PATH\""
    ;;
esac
