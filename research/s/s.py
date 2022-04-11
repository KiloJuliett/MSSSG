import io
import math
import os
import PIL.Image
import subprocess

WIDTH_MAXIMUM_GRAPHIC = 4000
STEP_WIDTH_GRAPHIC = 100
COUNT_QUALITIES = 101

image = PIL.Image.open("research/xkcd.png")

steps = math.floor(WIDTH_MAXIMUM_GRAPHIC / STEP_WIDTH_GRAPHIC)

data = {}

for index_step in range(steps):
    width = (index_step + 1) * STEP_WIDTH_GRAPHIC
    aspect = image.width / image.height
    height = round(width / aspect)

    path_image_resized = "research/q/w/w" + str(width) + ".png"

    image_resized = image.resize((width, height), PIL.Image.LANCZOS)
    image_resized.save(path_image_resized, format="PNG")

    os.mkdir("research/q/xkcd-jxl/" + str(width))

    data[str(width)] = {}

    for quality in range(COUNT_QUALITIES):
        # buffer = io.BytesIO()
        # image_resized.save(buffer, format="JPEG", quality=quality, optimize=True)
        # image_resized.save(buffer, format="WebP", quality=quality, method=6)
        # buffer = buffer.getvalue()

        # data[str(width)][str(quality)] = len(buffer)

        # path_image_jxl = "research/q/xkcd-jxl/jxl/w" + str(width) + "q" + str(quality) + ".jxl"
        # subprocess.run(
        #     "dependencies/jxlenc --min " + str(quality) + " --max " + str(quality) + " --minalpha " + str(quality) + " --maxalpha " + str(quality) + " -s 0 -j 4 " + path_image_resized + " " + path_image_jxl,
        #     stdout=subprocess.DEVNULL
        # )
        # data[str(width)][str(quality)] = os.path.getsize(path_image_jxl)
        # subprocess.run(
        #     "research/q/jxldec " + path_image_jxl + " research/q/xkcd-jxl/" + str(width) + "/" + str(quality) + ".png",
        #     stdout=subprocess.DEVNULL
        # )

        path_image_jxl = "research/q/xkcd-jxl/jxl/w" + str(width) + "q" + str(quality) + ".jxl"
        subprocess.run(
            "dependencies/cjxl " + path_image_resized + " " + path_image_jxl + " -q " + str(quality) + " -e 9",
            stdout=subprocess.DEVNULL
        )
        data[str(width)][str(quality)] = os.path.getsize(path_image_jxl)
        subprocess.run(
            "research/q/djxl " + path_image_jxl + " research/q/xkcd-jxl/" + str(width) + "/" + str(quality) + ".png",
            stdout=subprocess.DEVNULL
        )
    
    # buffer = io.BytesIO()
    # # image_resized.save(buffer, format="PNG", optimize=True)
    # image_resized.save(buffer, format="WebP", lossless=True, quality=100, method=6)
    # buffer = buffer.getvalue()

    # data[str(width)]["110"] = len(buffer)

    # path_image_jxl = "research/q/xkcd-jxl/jxl/w" + str(width) + "q" + str(110) + ".jxl"
    # subprocess.run(
    #     "dependencies/jxlenc -l -s 0 -j 4 " + path_image_resized + " " + path_image_jxl,
    #     stdout=subprocess.DEVNULL
    # )
    # data[str(width)]["110"] = os.path.getsize(path_image_jxl)
    # subprocess.run(
    #     "research/q/jxldec " + path_image_jxl + " research/q/xkcd-jxl/" + str(width) + "/" + str(110) + ".png",
    #     stdout=subprocess.DEVNULL
    # )

    path_image_jxl = "research/q/xkcd-jxl/jxl/w" + str(width) + "q" + str(110) + ".jxl"
    subprocess.run(
        "dependencies/cjxl " + path_image_resized + " " + path_image_jxl + " -q " + str(100) + " -e 9",
        stdout=subprocess.DEVNULL
    )
    data[str(width)]["110"] = os.path.getsize(path_image_jxl)
    subprocess.run(
        "research/q/djxl " + path_image_jxl + " research/q/xkcd-jxl/" + str(width) + "/" + str(110) + ".png",
        stdout=subprocess.DEVNULL
    )
    
    print(width)

output = open("o.tsv", "w")
output.write("\t" + "\t".join(data.keys()) + "\n")
for quality in data[str(STEP_WIDTH_GRAPHIC)].keys():
    output.write(quality)

    for width in data.keys():
        output.write("\t" + str(data[width][quality]))

    output.write("\n")


