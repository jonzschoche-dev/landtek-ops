#!/bin/bash
# Extract text from PDF then send to GPT-4o
for pdf in /root/landtek/inbox/*.pdf; do
  filename=$(basename "$pdf")
  echo "Extracting: $filename"
  
  # Extract text using pdftotext
  text=$(python3 -c "
import fitz
doc = fitz.open('$pdf')
text = ''
for page in doc:
    text += page.get_text()
print(text[:6000])
" 2>/dev/null)
  
  echo "Text length: ${#text} chars"
done
