#!/bin/bash
set -x -e -v

: NAME ${NAME:=firefox-profile}
: TEMPLATE ${TEMPLATE:=browsersupport/$NAME}
: PACKAGE ${PACKAGE:=org.mozilla.tv.firefox.gecko.debug}
: EXTERNAL ${EXTERNAL:=/mnt/sdcard}
: TMP ${TMP:=/tmp}
: URL ${URL:=https://example.com}
: SLEEP ${SLEEP:=120}  # In seconds.

for TURBO in true false ; do
    # This will kill the App so that we can safely remove the profile
    # directories created below.
    adb shell pm clear $PACKAGE
    adb shell pm grant $PACKAGE android.permission.WRITE_EXTERNAL_STORAGE
    adb shell pm grant $PACKAGE android.permission.READ_EXTERNAL_STORAGE

    adb shell rm -rf $EXTERNAL/$NAME-turbo-$TURBO
    adb push $TEMPLATE $EXTERNAL/$NAME-turbo-$TURBO

    adb shell am start -W -n $PACKAGE/org.mozilla.tv.firefox.MainActivity \
        -a android.intent.action.VIEW -d $URL \
        --ez TURBO_MODE $TURBO \
        --es args "'-profile $EXTERNAL/$NAME-turbo-$TURBO'"

    sleep $SLEEP

    # Kill the App so that we can safely pull the profile directory
    # created above.
    adb shell am force-stop $PACKAGE

    rm -rf $TMP/$NAME-turbo-$TURBO
    adb pull $EXTERNAL/$NAME-turbo-$TURBO $TMP/$NAME-turbo-$TURBO
done
