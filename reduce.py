#!/usr/bin/env python3

import argparse
import os
import shutil
import sys
import tempfile
import zipfile
from pathlib import Path
from PIL import Image
import xml.etree.ElementTree as ET
import re
from collections import defaultdict

def create_4bit_grayscale_png(input_path, output_path):
    """Convert image to 4-bit grayscale PNG"""
    try:
        with Image.open(input_path) as img:
            # Convert to grayscale and remove any color profiles
            grayscale = img.convert('L')
            
            # Create a new image to ensure clean profile
            clean_img = Image.new('L', grayscale.size)
            clean_img.paste(grayscale)
            
            # Reduce to 4-bit (16 levels) using quantization
            quantized = clean_img.quantize(colors=16, method=Image.Quantize.MEDIANCUT)
            
            # Create a clean grayscale palette for 16 levels
            palette = []
            for i in range(16):
                gray_value = int(i * 255 / 15)
                palette.extend([gray_value, gray_value, gray_value])
            
            # Pad palette to 256 colors (RGB triplets)
            while len(palette) < 768:
                palette.append(0)
            
            quantized.putpalette(palette)
            
            # Save as PNG without color profiles to avoid sRGB warnings
            pnginfo = None  # Remove any existing metadata/profiles
            quantized.save(output_path, 'PNG', optimize=True, pnginfo=pnginfo)
            return True
    except Exception as e:
        print(f"Error converting {input_path}: {e}")
        return False

def update_xml_references(file_path, image_mapping):
    """Update image references in XML/HTML files"""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        modified = False
        for old_path, new_path in image_mapping.items():
            old_filename = os.path.basename(old_path)
            new_filename = os.path.basename(new_path)
            
            # Update src attributes
            patterns = [
                rf'src="([^"]*/{re.escape(old_filename)})"',
                rf"src='([^']*/{re.escape(old_filename)})'",
                rf'src="(images/{re.escape(old_filename)})"',
                rf'src="(\.\./images/{re.escape(old_filename)})"',
                rf'src="(\./images/{re.escape(old_filename)})"'
            ]
            
            for pattern in patterns:
                new_content = re.sub(pattern, lambda m: f'src="{m.group(1).replace(old_filename, new_filename)}"', content)
                if new_content != content:
                    content = new_content
                    modified = True
        
        if modified:
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(content)
            return True
    except Exception as e:
        print(f"Error updating XML references in {file_path}: {e}")
    return False

def update_css_references(file_path, image_mapping):
    """Update image references in CSS files"""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        modified = False
        for old_path, new_path in image_mapping.items():
            old_filename = os.path.basename(old_path)
            new_filename = os.path.basename(new_path)
            
            # Update url() references
            patterns = [
                rf'url\("([^"]*/{re.escape(old_filename)})"\)',
                rf"url\('([^']*/{re.escape(old_filename)})'\)",
                rf'url\(([^)]*/{re.escape(old_filename)})\)'
            ]
            
            for pattern in patterns:
                new_content = re.sub(pattern, lambda m: f'url("{m.group(1).replace(old_filename, new_filename)}")', content)
                if new_content != content:
                    content = new_content
                    modified = True
        
        if modified:
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(content)
            return True
    except Exception as e:
        print(f"Error updating CSS references in {file_path}: {e}")
    return False

def update_opf_manifest(file_path, image_mapping):
    """Update manifest in OPF file with proper XML parsing"""
    try:
        # Parse XML
        tree = ET.parse(file_path)
        root = tree.getroot()
        
        # Find namespace
        ns = {'opf': 'http://www.idpf.org/2007/opf'}
        if root.tag.startswith('{'):
            ns_uri = root.tag.split('}')[0][1:]
            ns['opf'] = ns_uri
        
        # Find manifest
        manifest = root.find('.//opf:manifest', ns)
        if manifest is None:
            # Try without namespace
            manifest = root.find('.//manifest')
        
        if manifest is None:
            print("Could not find manifest in OPF file")
            return False
        
        modified = False
        
        # Update existing items
        for item in manifest.findall('.//opf:item', ns) or manifest.findall('.//item'):
            href = item.get('href', '')
            media_type = item.get('media-type', '')
            
            # Check if this is an image that was converted
            for old_path, new_path in image_mapping.items():
                if href.endswith(os.path.basename(old_path)):
                    # Update href to new PNG filename
                    new_href = href.replace(os.path.basename(old_path), os.path.basename(new_path))
                    item.set('href', new_href)
                    
                    # Update media-type to PNG
                    if media_type == 'image/jpeg':
                        item.set('media-type', 'image/png')
                    
                    modified = True
                    break
        
        if modified:
            # Write back with proper XML declaration
            tree.write(file_path, encoding='utf-8', xml_declaration=True)
            return True
            
    except Exception as e:
        print(f"Error updating OPF manifest in {file_path}: {e}")
    return False

def process_epub(epub_path, output_dir):
    """Process a single EPUB file"""
    epub_path = Path(epub_path)
    if not epub_path.exists():
        print(f"Error: File '{epub_path}' not found")
        return False
    
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    
    original_size = epub_path.stat().st_size
    basename = epub_path.stem
    
    print(f"Processing: {epub_path.name}")
    
    # Create temporary directories
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        extract_dir = temp_path / 'extracted'
        extract_dir.mkdir()
        
        try:
            # Extract EPUB
            print("Extracting epub...")
            with zipfile.ZipFile(epub_path, 'r') as zip_ref:
                zip_ref.extractall(extract_dir)
            
            # Find and convert images
            print("Processing images...")
            image_mapping = {}
            image_extensions = {'.png', '.jpg', '.jpeg'}
            
            for img_file in extract_dir.rglob('*'):
                if img_file.is_file() and img_file.suffix.lower() in image_extensions:
                    # Create PNG equivalent path
                    new_name = img_file.stem + '.png'
                    new_path = img_file.parent / new_name
                    
                    # Convert to 4-bit grayscale PNG
                    if create_4bit_grayscale_png(img_file, new_path):
                        # Store mapping for reference updating
                        rel_old_path = str(img_file.relative_to(extract_dir))
                        rel_new_path = str(new_path.relative_to(extract_dir))
                        image_mapping[rel_old_path] = rel_new_path
                        
                        # Remove original if different format
                        if img_file.suffix.lower() != '.png':
                            img_file.unlink()
                        
                        print(f"  Converted {img_file.name} -> {new_name}")
            
            if not image_mapping:
                print("  No images found to process")
            
            # Update references in content files
            if image_mapping:
                print("Updating file references...")
                
                # Update HTML/XHTML files
                for html_file in extract_dir.rglob('*.html'):
                    update_xml_references(html_file, image_mapping)
                for xhtml_file in extract_dir.rglob('*.xhtml'):
                    update_xml_references(xhtml_file, image_mapping)
                
                # Update CSS files
                for css_file in extract_dir.rglob('*.css'):
                    update_css_references(css_file, image_mapping)
                
                # Update OPF manifest files
                for opf_file in extract_dir.rglob('*.opf'):
                    update_opf_manifest(opf_file, image_mapping)
            
            # Create new EPUB with proper structure
            print("Repackaging epub...")
            output_epub = output_dir / f"{basename}.epub"
            
            with zipfile.ZipFile(output_epub, 'w', zipfile.ZIP_DEFLATED) as zip_out:
                # Add mimetype first (uncompressed)
                mimetype_file = extract_dir / 'mimetype'
                if mimetype_file.exists():
                    zip_out.write(mimetype_file, 'mimetype', compress_type=zipfile.ZIP_STORED)
                
                # Add all other files
                for file_path in extract_dir.rglob('*'):
                    if file_path.is_file() and file_path.name != 'mimetype':
                        arcname = str(file_path.relative_to(extract_dir))
                        zip_out.write(file_path, arcname)
            
            # Show results
            new_size = output_epub.stat().st_size
            size_diff = original_size - new_size
            percentage = int(size_diff * 100 / original_size) if original_size > 0 else 0
            
            print(f"Created: {output_epub}")
            print(f"Original size: {original_size / (1024*1024):.1f} MiB")
            print(f"New size: {new_size / (1024*1024):.1f} MiB")
            
            if size_diff > 0:
                print(f"Size reduction: {size_diff / (1024*1024):.1f} MiB ({percentage}%)")
            else:
                print(f"Size increase: {-size_diff / (1024*1024):.1f} MiB ({-percentage}%)")
            
            return True
            
        except Exception as e:
            print(f"Error processing {epub_path.name}: {e}")
            return False

def main():
    parser = argparse.ArgumentParser(description='Reduce EPUB file sizes by converting images to 4-bit grayscale PNG')
    parser.add_argument('epubs', nargs='+', help='EPUB file(s) to process')
    parser.add_argument('-o', '--output', default='output', help='Output directory (default: output)')
    
    args = parser.parse_args()
    
    # Create output directory
    output_dir = Path(args.output)
    output_dir.mkdir(exist_ok=True)
    
    # Process each EPUB
    successful = 0
    failed = 0
    
    for epub_path in args.epubs:
        print("=" * 50)
        if process_epub(epub_path, output_dir):
            successful += 1
        else:
            failed += 1
    
    # Summary
    if len(args.epubs) > 1:
        print("=" * 50)
        print("SUMMARY:")
        print(f"Successfully processed: {successful}")
        print(f"Failed: {failed}")

if __name__ == '__main__':
    main()