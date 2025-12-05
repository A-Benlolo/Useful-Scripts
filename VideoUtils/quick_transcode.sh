#!/usr/bin/env bash

for f in *.mkv; do
    [ -e "$f" ] || continue
    out="${f%.mkv}.mp4"
    ffmpeg -i "$f" -map 0 -map -0:s -c copy "$out"
done
