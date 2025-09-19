# EPUB 4-Bit Grayscale Converter

Reduces EPUB file sizes by converting all images to 4-bit grayscale PNG format.

## Usage

```bash
python3 epub-4bgs.py book1.epub book2.epub [...]
python3 epub-4bgs.py -o output_directory book.epub
```
Converted files get placed in a directory named output unless
you change the output directory with the -o argument. In
either case the output directory will be created if it doesn't
exist

## Requirements

- Python 3.6+
- Pillow (PIL)

```bash
pip install Pillow
```

## How it works

1. Extracts EPUB contents
2. Converts all images (PNG/JPG/JPEG) to 4-bit grayscale PNG
3. Updates image references in HTML, CSS, and manifest files
4. Repackages EPUB with size reduction statistics
