#!/bin/bash
set -x -e -v

# Invoke like `env ANDROID_SERIAL=... bash many.sh -n 3 -vv FILE`.

FILE="${@: -1}"
ARGS="${@:1:$#-1}"

cat "$FILE" | while read -r url; do
    # I'm pretty sure I'm not quoting arguments correctly, but I don't
    # know how to do it correctly.
    if [[ -n $url ]] && [[ $url != \#* ]] ; then
        /bin/bash wpr.sh $ARGS "$url" || echo "Failed to process $url; ignoring."
    fi
done
