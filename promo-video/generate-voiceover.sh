#!/bin/sh
# Generates one voiceover clip per scene into public/voiceover/ (requires: pip install edge-tts)
VOICE=en-US-AndrewNeural
RATE=+12%
gen() {
  for try in 1 2 3 4 5; do
    python -m edge_tts --voice "$VOICE" --rate="$RATE" --text "$2" --write-media "public/voiceover/$1.mp3" 2>/dev/null && return
  done
  echo "failed: $1" >&2; exit 1
}
gen 01-intro   "Meet StatEase. Statistics, without code."
gen 02-upload  "Upload your data. Every variable is detected."
gen 03-analyze "Paste your objectives. Get the right test."
gen 04-results "Results, written in A.P.A. style."
gen 05-export  "Export to Word and Excel."
gen 06-outro   "StatEase."
