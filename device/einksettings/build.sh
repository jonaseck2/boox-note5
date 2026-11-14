#!/bin/sh
# Build the E-ink Settings APK on macOS: aapt2 + javac + d8 + apksigner, no Gradle.
# Output: build/EinkSettings.apk. The SDK and the signing key live outside the repo.
set -eu
cd "$(dirname "$0")"

TOOLS=${BOOX_TOOLS:-$HOME/boox-backups/tools}
SDK=${ANDROID_SDK:-$TOOLS/android-sdk}
BT=$SDK/build-tools/36.1.0
JAR=$SDK/platforms/android-36/android.jar
KS=${EINK_KEYSTORE:-$TOOLS/einksettings.keystore}
KSPASS=boox-eink        # local self-signed key; the app is a system app, not a store release
export JAVA_HOME="${JAVA_HOME:-/opt/homebrew/opt/openjdk}"
export PATH="$JAVA_HOME/bin:$PATH"

# Fetch build-tools 36.1 and platform 36 (Android 16) from Google, SHA-1 checked against
# https://dl.google.com/android/repository/repository2-3.xml.
fetch() {   # fetch <zip> <sha1> <dest> <dir-in-zip>
  [ -e "$3" ] && return 0
  mkdir -p "$TOOLS/dl" "$(dirname "$3")"
  z=$TOOLS/dl/$1
  [ -e "$z" ] || curl -fsSL -o "$z" "https://dl.google.com/android/repository/$1"
  [ "$(shasum "$z" | cut -d' ' -f1)" = "$2" ] || { echo "SHA-1 mismatch: $z" >&2; exit 1; }
  t=$(mktemp -d "$TOOLS/dl/x.XXXXXX")
  unzip -q "$z" -d "$t"
  mv "$t/$4" "$3"
  rm -rf "$t"
}
fetch build-tools_r36.1_macosx.zip d365b05ca1810ca92b428b92717865ad4188b5e1 "$BT" android-16
fetch platform-36_r02.zip 2c1a80dd4d9f7d0e6dd336ec603d9b5c55a6f576 "$SDK/platforms/android-36" android-36
command -v javac >/dev/null || { echo "need a JDK: brew install openjdk" >&2; exit 1; }

rm -rf build
mkdir -p build/classes build/dex

"$BT/aapt2" link --manifest AndroidManifest.xml -I "$JAR" -o build/unsigned.apk

# shellcheck disable=SC2046
javac -nowarn -Xlint:none --release 11 -classpath "$JAR" -d build/classes $(find src -name '*.java')
# shellcheck disable=SC2046
"$BT/d8" --release --min-api 29 --lib "$JAR" --output build/dex $(find build/classes -name '*.class')
(cd build/dex && zip -q ../unsigned.apk classes.dex)

"$BT/zipalign" -f -p 4 build/unsigned.apk build/aligned.apk

if [ ! -e "$KS" ]; then
  keytool -genkeypair -keystore "$KS" -storepass "$KSPASS" -keypass "$KSPASS" -alias eink \
    -keyalg RSA -keysize 2048 -validity 36500 -dname "CN=Boox E-ink Settings" >/dev/null
fi
# Keep the same key across builds: Android refuses an update signed with a different key.
"$BT/apksigner" sign --ks "$KS" --ks-pass "pass:$KSPASS" --ks-key-alias eink \
  --out build/EinkSettings.apk build/aligned.apk 2>/dev/null
"$BT/apksigner" verify build/EinkSettings.apk 2>/dev/null
rm -f build/unsigned.apk build/aligned.apk build/EinkSettings.apk.idsig
echo "built $(pwd)/build/EinkSettings.apk ($(wc -c < build/EinkSettings.apk | tr -d ' ') bytes)"
