#!/bin/bash
set -x -e -v

# Invoke like `env ANDROID_SERIAL=... bash one.sh -n 3 -vv https://google.com`.

: PACKAGE ${PACKAGE:=org.mozilla.tv.firefox.gecko.debug}
# : EXTERNAL ${EXTERNAL:=/mnt/sdcard}
: TMP ${TMP:=/tmp}
: RESULT_TOP_DIR ${RESULT_TOP_DIR:=browsertime-results}
: ANDROID_SERIAL ${ANDROID_SERIAL:=ZX1G227GMF}
export ANDROID_SERIAL
: TURBO ${TURBO:=true false}
: BROWSER ${BROWSER:=firefox chrome}

URL=${@: -1}
URL=${URL#"https://"}
URL=${URL#"http://"}

# N.B.: yargs doesn't parse `--firefox.android.intentArgument --ez`
# properly, so always use `=--ez`!

if [[ $BROWSER == *"firefox"* ]] ; then
    for turbo in $TURBO ; do
        env RUST_BACKTRACE=1 RUST_LOG=trace bin/browsertime.js \
            --android \
            --skipHar \
            --firefox.geckodriverPath "/Users/nalexander/Mozilla/gecko/target/debug/geckodriver" \
            --firefox.android.deviceSerial="$ANDROID_SERIAL" \
            --firefox.android.package "org.mozilla.tv.firefox.gecko.debug" \
            --firefox.android.activity "org.mozilla.tv.firefox.MainActivity" \
            --firefox.android.intentArgument=--ez \
            --firefox.android.intentArgument=TURBO_MODE \
            --firefox.android.intentArgument=$turbo \
            --firefox.android.intentArgument=-a \
            --firefox.android.intentArgument=android.intent.action.VIEW \
            --firefox.android.intentArgument=-d \
            --firefox.android.intentArgument="data:," \
            --firefox.profileTemplate $TMP/gecko-profile-turbo-$turbo \
            --browser firefox \
            --resultDir "$RESULT_TOP_DIR/firefox/$turbo/$URL" \
            "$@"
    done
fi

# N.B.: chromedriver doesn't have an official way to pass intent
# arguments, but it does have an unsanitized injection at
# https://github.com/bayandin/chromedriver/blob/5a2b8f793391c80c9d1a1b0004f28be0a2be9ab2/chrome/adb_impl.cc#L212.

if [[ $BROWSER == *"chrome"* ]] ; then
    for turbo in $TURBO ; do
        bin/browsertime.js \
            --android \
            --skipHar \
            --chrome.chromedriverPath "/Users/nalexander/Downloads/chromedriver-2.32" \
            --chrome.android.deviceSerial="$ANDROID_SERIAL" \
            --chrome.android.package "org.mozilla.tv.firefox.debug" \
            --chrome.android.activity="org.mozilla.tv.firefox.MainActivity --ez TURBO_MODE false -a android.intent.action.VIEW" \
            --browser chrome \
            --resultDir "$RESULT_TOP_DIR/chrome/$turbo/$URL" \
            "$@"
    done
fi
