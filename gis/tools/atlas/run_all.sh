#!/bin/bash
# Rebuild the Camarines Norte tie point atlas end to end (~15 min; fetches Esri basemap tiles).
set -e
cd "$(dirname "$0")"
mkdir -p build
python3 qa_boundaries.py
python3 sheet_overview.py > build/log_overview.txt 2>&1 &
printf '%s\n' "Basud" "Capalonga" "Daet" "Jose Panganiban" "Labo" "Mercedes" "Paracale" \
  "San Lorenzo Ruiz" "San Vicente" "Santa Elena" "Talisay" "Vinzons" \
  | xargs -P 4 -I{} sh -c 'python3 sheet_detail.py "{}" > "build/log_{}.txt" 2>&1'
wait
# Recompress raster basemaps to JPEG at 160 dpi — vectors and text untouched (~200 MB -> ~18 MB)
for f in build/sheet_*.pdf; do
  gs -q -dNOPAUSE -dBATCH -sDEVICE=pdfwrite -dCompatibilityLevel=1.6 \
     -dAutoFilterColorImages=false -dColorImageFilter=/DCTEncode -dJPEGQ=82 \
     -dDownsampleColorImages=true -dColorImageDownsampleType=/Bicubic -dColorImageResolution=160 \
     -dColorImageDownsampleThreshold=1.2 -dAutoFilterGrayImages=false -dGrayImageFilter=/DCTEncode \
     -dEmbedAllFonts=true -dSubsetFonts=true -sOutputFile="$f.tmp" "$f" && mv "$f.tmp" "$f"
done
python3 appendix.py
python3 merge.py
echo "atlas -> build/cn_tiepoints_atlas_v1.0.0.pdf"
