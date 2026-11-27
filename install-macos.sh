#!/bin/sh
# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Install a published native Mac app in the user's Applications directory.
set -eu
[ "$(uname -s)" = Darwin ] || { echo 'Dieser Installer ist für macOS.' >&2; exit 1; }
case "$(uname -m)" in arm64) TASK_ARCH=arm64;; x86_64) TASK_ARCH=x86_64;; *) echo 'Nicht unterstützte Architektur.' >&2; exit 1;; esac
TASK_TMP=$(mktemp -d)
TASK_MOUNTED=0
cleanup() {
  if [ "$TASK_MOUNTED" = 1 ]; then hdiutil detach "$TASK_TMP/mount" >/dev/null 2>&1 || return; fi
  rm -rf "$TASK_TMP"
}
trap cleanup EXIT HUP INT TERM
TASK_REPO=https://github.com/Niklas-Gr-231/cfs-tagwriter
TASK_URL=$(curl --fail --silent --show-error --location --proto '=https' --proto-redir '=https' --output /dev/null --write-out '%{url_effective}' "$TASK_REPO/releases/latest")
TASK_TAG=${TASK_URL##*/}
printf '%s\n' "$TASK_TAG" | grep -Eq '^v(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$' || { echo 'Keine stabile Version gefunden.' >&2; exit 1; }
TASK_FILE="CFS_Tagwriter_${TASK_TAG#v}_macos-${TASK_ARCH}.dmg"
curl --fail --location --proto '=https' --proto-redir '=https' "$TASK_REPO/releases/download/$TASK_TAG/$TASK_FILE" --output "$TASK_TMP/$TASK_FILE"
curl --fail --silent --show-error --location --proto '=https' --proto-redir '=https' "$TASK_REPO/releases/download/$TASK_TAG/$TASK_FILE.sha256" --output "$TASK_TMP/check.sha256"
TASK_EXPECTED=$(cut -d ' ' -f 1 "$TASK_TMP/check.sha256")
TASK_ACTUAL=$(shasum -a 256 "$TASK_TMP/$TASK_FILE" | cut -d ' ' -f 1)
[ "$TASK_EXPECTED" = "$TASK_ACTUAL" ] || { echo 'Prüfsumme falsch. Installation abgebrochen.' >&2; exit 1; }
mkdir "$TASK_TMP/mount"
hdiutil attach -nobrowse -readonly -mountpoint "$TASK_TMP/mount" "$TASK_TMP/$TASK_FILE" >/dev/null
TASK_MOUNTED=1
TASK_DEST="$HOME/Applications"
mkdir -p "$TASK_DEST"
if [ -e "$TASK_DEST/CFS Tagwriter.app" ]; then
  hdiutil detach "$TASK_TMP/mount" >/dev/null
TASK_MOUNTED=0
  echo 'Die App ist bereits installiert. Bitte über Einstellungen → App aktualisieren fortfahren.' >&2
  exit 1
fi
if ! ditto "$TASK_TMP/mount/CFS Tagwriter.app" "$TASK_DEST/CFS Tagwriter.app"; then
  hdiutil detach "$TASK_TMP/mount" >/dev/null
TASK_MOUNTED=0
  echo 'Kopieren fehlgeschlagen. Bitte die DMG im Finder öffnen.' >&2; exit 1
fi
hdiutil detach "$TASK_TMP/mount" >/dev/null
TASK_MOUNTED=0
printf 'Installiert: %s\nUpdates: Einstellungen → App aktualisieren\n' "$TASK_DEST/CFS Tagwriter.app"
open "$TASK_DEST/CFS Tagwriter.app"
