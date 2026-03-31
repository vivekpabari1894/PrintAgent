"""Generate agent_icon.ico from agent_logo.png for PyInstaller."""
from PIL import Image
import sys

img = Image.open('agent_logo.png').convert('RGBA')

# Make white pixels transparent  
pixels = img.load()
w, h = img.size
for x in range(w):
    for y in range(h):
        r, g, b, a = pixels[x, y]
        if r > 230 and g > 230 and b > 230:
            pixels[x, y] = (255, 255, 255, 0)

# Make square
size = max(w, h)
square = Image.new('RGBA', (size, size), (0, 0, 0, 0))
square.paste(img, ((size - w) // 2, (size - h) // 2))

# Resize to standard ICO sizes and save
icon_sizes = [(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]
imgs = []
for s in icon_sizes:
    resized = square.resize(s, Image.LANCZOS)
    imgs.append(resized)

# Save - the first image is the "main" one, append_images adds the rest
imgs[0].save('agent_icon.ico', format='ICO', append_images=imgs[1:])

print(f"Generated agent_icon.ico successfully")
print(f"Source: {w}x{h}, Square: {size}x{size}")
import os
print(f"File size: {os.path.getsize('agent_icon.ico')} bytes")
