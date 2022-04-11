import math
import numpy
import PIL.Image
import skimage.metrics

WIDTH_MAXIMUM_GRAPHIC = 4000
STEP_WIDTH_GRAPHIC = 100
IMAGE = "xkcd"
FORMATS = [
    ("jpeg", "jpeg", "png", 101),
    ("webp", "webp", "webp", 101),
    # ("avif", "png", "png", 64),
    # ("jxl", "png", "png", 101),
]

image = PIL.Image.open("research/" + IMAGE + ".png")

steps = math.floor(WIDTH_MAXIMUM_GRAPHIC / STEP_WIDTH_GRAPHIC)

for format in FORMATS:
    data = {}

    for index_step in range(steps):
        width = (index_step + 1) * STEP_WIDTH_GRAPHIC
        aspect = image.width / image.height
        height = round(width / aspect)

        data[str(width)] = {}

        path_image_resized = "research/q/w/w" + str(width) + ".png"
        image_resized = image.resize((width, height), PIL.Image.LANCZOS)
        image_resized = image_resized.convert(mode="RGB")
        data_image_resized = numpy.asarray(image_resized)

        for quality in range(format[3]):
            print(format[0] + " " + str(width) + " " + str(quality) + "         ", end="\r")

            path_image_compressed = "research/q/" + IMAGE + "-" + format[0] + "/" + str(width) + "/" + str(quality) + "." + format[1]
            image_compressed = PIL.Image.open(path_image_compressed)
            image_compressed = image_compressed.convert(mode="RGB")
            data_image_compressed = numpy.asarray(image_compressed)

            ssim = skimage.metrics.structural_similarity(data_image_resized, data_image_compressed, channel_axis=2)

            data[str(width)][str(quality)] = ssim
        
        path_image_compressed = "research/q/" + IMAGE + "-" + format[0] + "/" + str(width) + "/" + str(110) + "." + format[2]
        image_compressed = PIL.Image.open(path_image_compressed)
        image_compressed = image_compressed.convert(mode="RGB")
        data_image_compressed = numpy.asarray(image_compressed)

        ssim = skimage.metrics.structural_similarity(data_image_resized, data_image_compressed, channel_axis=2)

        data[str(width)][str(110)] = ssim

    output = open("output-ssim-" + IMAGE + "-" + format[0] + ".tsv", "w")
    output.write("\t" + "\t".join(data.keys()) + "\n")
    for quality in data[str(STEP_WIDTH_GRAPHIC)].keys():
        output.write(quality)

        for width in data.keys():
            output.write("\t" + str(data[width][quality]))

        output.write("\n")
