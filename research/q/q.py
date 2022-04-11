import io
import math
import os
import PIL.Image
import subprocess
COUNT_QUALITIES = 101

image = PIL.Image.open("research/tiff.png")

for quality in range(COUNT_QUALITIES):
    path = "research/q/tiff-jpeg/" + str(quality) + ".jpeg"
    image.save(path, format="JPEG", quality=quality, optimize=True)

    path = "research/q/tiff-webp/" + str(quality) + ".webp"
    image.save(path, format="WebP", quality=quality, method=6)

    print(quality)

# buffer = io.BytesIO()
# image.save(buffer, format="PNG", optimize=True)
# buffer = buffer.getvalue()