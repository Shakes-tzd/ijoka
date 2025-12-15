#!/bin/bash
# Generate PWA icons from SVG
# Requires: rsvg-convert (librsvg) or ImageMagick

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
STATIC_DIR="$SCRIPT_DIR/../priv/static/images"
SVG_FILE="$STATIC_DIR/icon.svg"

SIZES=(16 32 72 96 128 144 152 192 384 512)

echo "Generating PWA icons..."

# Check for rsvg-convert (preferred)
if command -v rsvg-convert &> /dev/null; then
    for size in "${SIZES[@]}"; do
        echo "  Creating icon-${size}.png"
        rsvg-convert -w "$size" -h "$size" "$SVG_FILE" -o "$STATIC_DIR/icon-${size}.png"
    done
    echo "Done! Icons generated using rsvg-convert"

# Fallback to ImageMagick
elif command -v convert &> /dev/null; then
    for size in "${SIZES[@]}"; do
        echo "  Creating icon-${size}.png"
        convert -background none -resize "${size}x${size}" "$SVG_FILE" "$STATIC_DIR/icon-${size}.png"
    done
    echo "Done! Icons generated using ImageMagick"

# Fallback to sips (macOS built-in) - needs PNG input
elif command -v sips &> /dev/null; then
    echo "sips found but requires PNG input. Please install librsvg or ImageMagick:"
    echo "  brew install librsvg"
    echo "  # or"
    echo "  brew install imagemagick"
    exit 1

else
    echo "No image conversion tool found. Please install:"
    echo "  brew install librsvg"
    echo "  # or"
    echo "  brew install imagemagick"
    exit 1
fi

echo ""
echo "Generated icons:"
ls -la "$STATIC_DIR"/icon-*.png 2>/dev/null || echo "No icons found"
