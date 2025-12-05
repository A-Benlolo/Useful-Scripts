#!/bin/bash

# Get the current directory
dir=$(pwd)

# Loop through all MKV files in the current directory
for file in *.mkv; do
    # Skip if no MKV files are found
    [ -e "$file" ] || continue

    # Extract the filename without extension
    filename="${file%.mkv}"

    # Find the first subtitle stream and determine its codec
    stream_info=$(ffprobe -loglevel error -select_streams s -show_entries stream=index,codec_name -of csv=p=0 "$file" | head -n 1)

    # Extract stream index and codec name
    stream=$(echo "$stream_info" | cut -d',' -f1)
    codec=$(echo "$stream_info" | cut -d',' -f2)

    # Check if a subtitle stream was found
    if [ -z "$stream" ]; then
        echo "No subtitle stream found in: $file"
        continue
    fi

    # Determine the correct subtitle format and extension
    case "$codec" in
        hdmv_pgs_subtitle)
            output="${filename}.eng.sup"
            ;;
        subrip)
            output="${filename}.eng.srt"
            ;;
        ass)
            output="${filename}.eng.ass"
            ;;
        *)
            echo "Unsupported subtitle format ($codec) in: $file"
            continue
            ;;
    esac

    # Extract the subtitle stream
    echo "Extracting $codec subtitles from: $file (Stream $stream) -> $output"
    ffmpeg -i "$file" -map 0:"$stream" -c copy "$output" &> /dev/null

    # Check if extraction was successful
    if [ $? -eq 0 ]; then
        echo "Successfully extracted: $output"
    else
        echo "Failed to extract subtitles from: $file"
    fi
done
