#!/bin/sh
# Build the e-ink resource overlays (static RROs, no code) with the same SDK and key as einksettings.
set -eu
cd "$(dirname "$0")"
TOOLS=${BOOX_TOOLS:-$HOME/boox-backups/tools}
SDK=${ANDROID_SDK:-$TOOLS/android-sdk}
BT=$SDK/build-tools/36.1.0
JAR=$SDK/platforms/android-36/android.jar
KS=${EINK_KEYSTORE:-$TOOLS/einksettings.keystore}
KSPASS=${EINK_KSPASS:-boox-eink}
[ -z "${JAVA_HOME:-}" ] && [ -d /opt/homebrew/opt/openjdk ] && JAVA_HOME=/opt/homebrew/opt/openjdk
[ -n "${JAVA_HOME:-}" ] && export JAVA_HOME && export PATH="$JAVA_HOME/bin:$PATH"
[ -x "$BT/aapt2" ] || ../einksettings/build.sh >/dev/null   # fetches the SDK on first use
mkdir -p build
for t in launcher systemui framework; do
  rm -rf "build/$t" && mkdir -p "build/$t"
  "$BT/aapt2" compile --dir "$t/res" -o "build/$t/res.zip"
  "$BT/aapt2" link --manifest "$t/AndroidManifest.xml" -I "$JAR" -o "build/$t/unsigned.apk" "build/$t/res.zip"
  "$BT/zipalign" -f -p 4 "build/$t/unsigned.apk" "build/$t/aligned.apk"
  "$BT/apksigner" sign --ks "$KS" --ks-pass "pass:$KSPASS" --ks-key-alias eink --out "build/BooxEink-$t.apk" "build/$t/aligned.apk"
  echo "built build/BooxEink-$t.apk"
done
