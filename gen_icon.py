"""Generate agent_icon.ico from agent_logo.png.
Uses raw ICO binary format with embedded PNGs for maximum compatibility."""
from PIL import Image
import struct
import io
import os

def create_ico(input_path, output_path, sizes=None):
    """Create a valid Windows ICO file with embedded PNG data."""
    if sizes is None:
        sizes = [16, 32, 48, 64, 128, 256]
    
    img = Image.open(input_path).convert('RGBA')
    
    # Make white pixels transparent
    pixels = img.load()
    w, h = img.size
    for x in range(w):
        for y in range(h):
            r, g, b, a = pixels[x, y]
            if r > 230 and g > 230 and b > 230:
                pixels[x, y] = (255, 255, 255, 0)
    
    # Make square
    max_dim = max(w, h)
    square = Image.new('RGBA', (max_dim, max_dim), (0, 0, 0, 0))
    square.paste(img, ((max_dim - w) // 2, (max_dim - h) // 2))
    
    # Generate PNG data for each size
    png_data_list = []
    for size in sizes:
        resized = square.resize((size, size), Image.LANCZOS)
        buf = io.BytesIO()
        resized.save(buf, format='PNG')
        png_data_list.append(buf.getvalue())
    
    # Build ICO file manually
    # ICO Header: reserved(2) + type(2) + count(2)
    num_images = len(sizes)
    header = struct.pack('<HHH', 0, 1, num_images)
    
    # Calculate offsets
    # Header is 6 bytes, each directory entry is 16 bytes
    data_offset = 6 + (16 * num_images)
    
    directory = b''
    image_data = b''
    
    for i, size in enumerate(sizes):
        png_bytes = png_data_list[i]
        # Width and Height: 0 means 256
        w_byte = 0 if size >= 256 else size
        h_byte = 0 if size >= 256 else size
        
        # Directory entry: width(1) + height(1) + colors(1) + reserved(1) + 
        #                   planes(2) + bpp(2) + size(4) + offset(4)
        entry = struct.pack('<BBBBHHII',
            w_byte, h_byte, 0, 0,  # width, height, colors, reserved
            1, 32,                   # planes, bits per pixel
            len(png_bytes),          # size of PNG data
            data_offset + len(image_data)  # offset from start of file
        )
        directory += entry
        image_data += png_bytes
    
    # Write the ICO file
    with open(output_path, 'wb') as f:
        f.write(header)
        f.write(directory)
        f.write(image_data)
    
    file_size = os.path.getsize(output_path)
    print(f"Generated {output_path}: {file_size} bytes, {num_images} sizes")
    
    # Verify first bytes
    with open(output_path, 'rb') as f:
        magic = f.read(4)
        if magic == b'\x00\x00\x01\x00':
            print("ICO header verified: valid")
        else:
            print(f"WARNING: Invalid ICO header: {magic.hex()}")

if __name__ == '__main__':
    create_ico('agent_logo.png', 'agent_icon.ico')
