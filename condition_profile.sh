#!/bin/bash
set -x -e -v

: NAME ${NAME:=firefox-profile}
: TEMPLATE ${TEMPLATE:=browsersupport/$NAME}
# : PACKAGE ${PACKAGE:=org.mozilla.tv.firefox.gecko.debug}
: PACKAGE ${PACKAGE:=org.mozilla.firefox}
: EXTERNAL ${EXTERNAL:=/mnt/sdcard}
: TMP ${TMP:=/tmp}
: URL ${URL:=https://example.com}
: SLEEP ${SLEEP:=120}  # In seconds.

# This will kill the App so that we can safely remove the profile
# directories created below.
adb shell pm clear $PACKAGE
adb shell pm grant $PACKAGE android.permission.WRITE_EXTERNAL_STORAGE
adb shell pm grant $PACKAGE android.permission.READ_EXTERNAL_STORAGE

adb shell rm -rf $EXTERNAL/$NAME
adb push $TEMPLATE $EXTERNAL/$NAME

adb shell am start -W -n $PACKAGE/.App \
    -a android.intent.action.VIEW -d $URL \
    --ez skipstartpane true \
    --es args "'-profile $EXTERNAL/$NAME'"

sleep $SLEEP

# Kill the App so that we can safely pull the profile directory
# created above.
adb shell am force-stop $PACKAGE

rm -rf $TMP/$NAME
adb pull $EXTERNAL/$NAME $TMP/$NAME
