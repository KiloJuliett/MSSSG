import astropy.time
import base64
import bisect
import brotli
import gzip
import hashlib
import io
import itertools
import json
import lxml.cssselect as cssselect
import lxml.html as html
import lxml.etree as xml
import math
import minify_html
import multiprocessing
import multiprocessing.managers
import multiprocessing.shared_memory
import os
import pathlib
import PIL.Image
import signal
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import threading
import time
import zlib
import traceback

## Whether the output website uses a dynamic runtime.
DYNAMIC_OUTPUT = True

## The hashing algorithm to use.
ALGORITHM_HASH = "sha3_256"

## A salt for hashing.
SALT_HASH = b"I prefer sugar personally"

## The URI prefix for assets.
PREFIX_URI_ASSET = "a/"

## The length of asset IDs.
LENGTH_ID_ASSET = 16

## The available encoding methods.
ENCODERS_ENCODING = {
    "gzip": lambda data: gzip.compress(data),
    "deflate": lambda data: zlib.compress(data, level=9),
    "br": lambda data: brotli.compress(data),
}

## The threshold at which point the builder will prefer to store encoded
## resources as files in the filesystem instead of as blobs in the database.
THRESHOLD_ENCODING = 100000

## The step size of the widths of the rendered graphic images.
STEP_WIDTH_GRAPHIC = 100

## Quality settings for graphic renders.
QUALITIES_GRAPHIC = {
    "image/png": {
        "LOSSLESS": None,
    },
    "image/jpeg": {
        "LOW": {
            1000: 62,
            2000: 48,
            3000: 38,
            4000: 32,
        },
        "MEDIUM": {
            1000: 84,
            2000: 79,
            3000: 72,
            4000: 68,
        },
        "HIGH": {
            1000: 96,
            2000: 94,
            3000: 92,
            4000: 90,
        },
    },
    "image/webp": {
        "LOW": {
            1000: 40,
            2000: 35,
            3000: 31,
            4000: 26,
        },
        "MEDIUM": {
            1000: 76,
            2000: 76,
            3000: 73,
            4000: 69,
        },
        "HIGH": {
            1000: 92,
            2000: 91,
            3000: 90,
            4000: 90,
        },
        "LOSSLESS": None,
    },
}

## The preferred width of the fallback graphic image.
WIDTH_FALLBACK_GRAPHIC = 1200

## The maximum width of a generated graphic image.
WIDTH_MAXIMUM_GRAPHIC = 4000

# Sanity checks on the constants.
assert WIDTH_FALLBACK_GRAPHIC % STEP_WIDTH_GRAPHIC == 0
assert WIDTH_MAXIMUM_GRAPHIC % STEP_WIDTH_GRAPHIC == 0

## Draws a cute loading animation. 哇！好可爱的！
def animate():
    FPS = 60
    RATE = 1
    GAMMA = 2.2
    FRAMES_PART = 5
    FRAMES_TRANSITION = 2.5
    COLOR = (0, 255, 205)
    LEVEL_BACKGROUND = 0.15
    MESSAGE = "Building"

    # Let the main process deal with interrupts.
    signal.signal(signal.SIGINT, signal.SIG_IGN)

    code_color = ";".join(map(str, COLOR))

    frame = 0
    while True:
        is_part = lambda component: (
            FRAMES_PART * component <= frame < FRAMES_PART * (component + 1)
        )

        frame_transition_start = FRAMES_PART - FRAMES_TRANSITION
        frame_part = frame % FRAMES_PART
        transition = 0 \
            if frame_part < frame_transition_start \
            else (frame_part - frame_transition_start) / FRAMES_TRANSITION

        part = (1 * (1 - transition), 1 * transition)

        if is_part(0):
            bitmap = [0, 0, part[0], part[1]]
        elif is_part(1):
            bitmap = [0, part[1], 0, part[0]]
        elif is_part(2):
            bitmap = [part[1], part[0], 0, 0]
        elif is_part(3):
            bitmap = [part[0], 0, part[1], 0]

        assert all(0 <= level <= 1 for level in bitmap)

        bitmap = list(map(
            lambda level: ";".join(map(
                lambda component:
                    str(int(
                        (LEVEL_BACKGROUND + (1 - LEVEL_BACKGROUND) * level**GAMMA)
                        * component
                    )),
                COLOR
            )),
            bitmap
        ))

        def character(lower, upper):
            return "\x1B[38;2;" + lower + ";48;2;" + upper + "m" + "\u2584\x1B[0m"

        print(
            character(bitmap[0], bitmap[2])
            + character(bitmap[1], bitmap[3])
            + " \x1B[38;2;" + code_color + "m" + MESSAGE + "...\x1B[0m ",
            end="\r"
        )

        frame += RATE
        if frame >= FRAMES_PART * 4:
            frame = 0
        time.sleep(1 / FPS)

## Initializes a worker process.
def initializer():
    # Let the main process deal with interrupts.
    signal.signal(signal.SIGINT, signal.SIG_IGN)

## Reads the given file into memory and returns it.
def data_file(path):
    data = b""
    file = open(path, "rb")
    while buffer := file.read():
        data += buffer
    file.close()

    return data

## Hashes the given data.
def hash(data):
    hasher = hashlib.new(ALGORITHM_HASH)
    hasher.update(SALT_HASH)
    hasher.update(data)

    return hasher.digest()

## Encodes the given data using the given encoding method.
def encode(data, encoding):
    return ENCODERS_ENCODING[encoding](data)

## Rerenders the given image with the given specifications.
def render_image(data, type, width, quality):
    assert isinstance(width, int) or width.is_integer()

    match quality:
        case "VERY LOW" | "LOW" | "MEDIUM" | "HIGH" | "VERY HIGH" | "LOSSLESS":
            pass
        case _:
            raise RuntimeError("Unknown quality: " + quality)
    if not quality in QUALITIES_GRAPHIC[type]:
        raise RuntimeError("Unsupported quality for " + type + ": " + quality)

    definition_quality = QUALITIES_GRAPHIC[type][quality]

    if isinstance(definition_quality, dict):
        widths = sorted(definition_quality.keys())
        
        index_width = bisect.bisect_right(widths, width)

        # Calculate interpolant.
        if index_width == 0:
            value_quality = definition_quality[widths[0]]
        elif index_width == len(widths):
            value_quality = definition_quality[widths[len(widths) - 1]]
        else:
            value_quality = round(
                definition_quality[widths[index_width - 1]] \
                + (definition_quality[widths[index_width]] - definition_quality[widths[index_width - 1]]) \
                    * (width - widths[index_width - 1]) \
                    / (widths[index_width] - widths[index_width - 1])
            )
    else:
        value_quality = definition_quality

    # TODO is `PIL.Image` pickleable?
    image = PIL.Image.open(io.BytesIO(data))

    if width > image.width:
        # TODO maybe this should only be a warning instead?
        raise RuntimeError("Rendered image resolution limited by source resolution")

    # TODO strip metadata

    if width != image.width:
        aspect = image.width / image.height

        height = round(width / aspect)

        image = image.resize((width, height), PIL.Image.LANCZOS)

    output = io.BytesIO()

    match type:
        case "image/png":
            image.save(output, format="PNG", optimize=True)
        case "image/jpeg":
            image.save(output, format="JPEG", quality=value_quality, optimize=True)
        # case "image/jpeg2000":
        #     image.save(output, format="JPEG2000", irreversible=False)
        case "image/webp":
            if quality == "LOSSLESS":
                image.save(output, format="WebP", lossless=True, quality=100, method=6)
            else:
                image.save(output, format="WebP", quality=value_quality, method=6)
        case "image/avif":
            directory = tempfile.TemporaryDirectory()

            image.save(directory.name + "/input.png", format="PNG")
            image.close()

            subprocess.run(
                "dependencies/avifenc -l -s 0 -j " + str(os.cpu_count()) + " " + directory.name + "/input.png " + directory.name + "/output.avif",
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )

            output.write(data_file(directory.name + "/output.avif"))

            directory.cleanup()

        case "image/jxl":
            directory = tempfile.TemporaryDirectory()

            image.save(directory.name + "/input.png", format="PNG")
            image.close()

            subprocess.run(
                "dependencies/cjxl " + directory.name + "/input.png " + directory.name + "/output.jxl -q 100 -e 9",
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )

            output.write(data_file(directory.name + "/output.jxl"))

            directory.cleanup()

        case _:
            raise RuntimeError("Unknown type " + type)

    data = output.getvalue()

    output.close()
    image.close()

    return data

def main():
    try:
        time_start = time.monotonic()

        animator = multiprocessing.Process(target=animate)
        animator.start()

        revision = astropy.time.Time.now()
        revision.format = "unix_tai"
        revision = float(str(revision))

        pool = multiprocessing.Pool(initializer=initializer)

        lock = threading.Lock()

        ## A parallel asynchronous task backed by a process.
        class PTask:
            ## Creates a new p-task and starts it.
            def __init__(self, function, arguments):
                self.event = threading.Event()

                def callback(_):
                    self.event.set()

                self.result = pool.apply_async(
                    function,
                    args=arguments,
                    callback=callback,
                    error_callback=callback
                )

            ## Awaits the result of this p-task.
            def wait(self):
                FREQUENCY = 5

                # For some stupid fucking reason, `AsyncResult.get` and
                # `AsyncResult.wait` never raise `KeyboardInterrupt`, and so the
                # workaround is to use events instead. Sometimes, I feel like
                # using Python is less "using" it and more "fighting" it...
                while not self.event.wait(1 / FREQUENCY):
                    pass

                return self.result.get()

        ## A non-parallel asynchronous task backed by a thread.
        class NTask:
            ## Creates a new n-task and starts it.
            def __init__(self, function, arguments):
                # TODO maybe using a threadpool might be more efficient.

                def runner(ntask, function, arguments):
                    try:
                        result = function(*arguments)

                        ntask.success = True
                        self.result = result
                    except Exception as exception:
                        ntask.success = False
                        self.result = exception

                self.thread = threading.Thread(
                    target=runner,
                    args=(self, function, arguments),
                    daemon=True
                )
                self.thread.start()

            ## Awaits the result of this n-task.
            def wait(self):
                FREQUENCY = 5

                while True:
                    # What an incredibly annoying language Python is. I honestly
                    # wonder if I've sunken-cost-fallacy'd myself into throwing
                    # more time into getting around Python's foibles instead of,
                    # say, rewriting everything in Ruby or something.
                    self.thread.join(1 / FREQUENCY)
                    if not self.thread.is_alive():
                        break

                if self.success:
                    return self.result
                else:
                    raise self.result

        if os.path.exists("www"):
            shutil.rmtree("www")
        
        os.mkdir("www")
        os.mkdir("www/resources")

        database = sqlite3.connect(
            ":memory:",
            timeout=30,
            isolation_level=None,
            check_same_thread=False
        )
        database.executescript('''
            PRAGMA foreign_keys = 1;
            PRAGMA analysis_limit = 0;

            CREATE TABLE uris (
                uri TEXT,
                action TEXT NOT NULL,
                cache TEXT NOT NULL,
                PRIMARY KEY (uri),
                CHECK (action IN ("RESOURCE", "REDIRECT", "DELETION")),
                CHECK (cache IN ("NONE", "SHORT", "MEDIUM", "LONG", "INDEFINITE"))
            );
            CREATE TABLE resources (
                uri TEXT,
                type TEXT NOT NULL,
                etag TEXT NOT NULL,
                PRIMARY KEY (uri),
                FOREIGN KEY (uri) REFERENCES uris(uri)
            );
            CREATE TABLE encodings (
                uri TEXT,
                encoding TEXT NOT NULL,
                location TEXT NOT NULL,
                data BLOB,
                length INTEGER NOT NULL,
                UNIQUE(uri, encoding),
                FOREIGN KEY (uri) REFERENCES uris(uri),
                CHECK (location IN ("DATABASE", "FILESYSTEM"))
            );
            CREATE TABLE redirects (
                uri TEXT ,
                type TEXT NOT NULL,
                location TEXT NOT NULL,
                PRIMARY KEY (uri),
                FOREIGN KEY (uri) REFERENCES uris(uri),
                CHECK (type IN ("TEMPORARY", "PERMANENT"))
            );
        ''')

        database_disk = sqlite3.connect("www/database.db")

        shutil.copy("src/server.php", "www/main.php")

        if not os.path.exists("msssg"):
            os.mkdir("msssg")
        
        if not os.path.exists("msssg/assets"):
            os.mkdir("msssg/assets")
        
        if os.path.exists("msssg/history_assets.json"):
            history_assets = json.load(open("msssg/history_assets.json", "r"))
        else:
            history_assets = {}

        if os.path.exists("msssg/data_assets.json"):
            data_assets = json.load(open("msssg/data_assets.json", "r"))
        else:
            data_assets = {}

        assets = {}

        links = json.load(open("src/links.json"))

        if not "~notfound" in links:
            raise RuntimeError("Links must contain ~notfound")

        ## Inserts a resource into the database.
        def insert_resource(data, type, cache, uri="", encoded=True):
            id = hash(data + uri.encode("UTF-8"))[:LENGTH_ID_ASSET]

            if uri == "":
                uri = "/" + PREFIX_URI_ASSET + base64.urlsafe_b64encode(id).decode("UTF-8").replace("=", "")
                etag = "\"\""

                # TODO I'm not sure I want to make this a hard requirement
                assert cache == "INDEFINITE"
            else:
                etag = "\"" + base64.b85encode(id).decode("UTF-8") + "\""

            database.execute('''
                INSERT INTO uris (
                    uri,
                    action,
                    cache
                )
                VALUES (
                    ?, "RESOURCE", ?
                )
            ''', (uri, cache))

            database.execute('''
                INSERT INTO resources (
                    uri,
                    type,
                    etag
                )
                VALUES (?, ?, ?)
            ''', (uri, type, etag))

            ## Inserts the given encoding into the database.
            def insert_encoding(data_encoding, encoding):
                location = "DATABASE"
                length_data = len(data_encoding)

                # Decide location for the file.
                if length_data > THRESHOLD_ENCODING:
                    # Data is too big to be efficiently handled by the
                    # database; put it in the filesystem instead.

                    # Oh you, Windows...
                    filename = base64.b32encode(id).decode("UTF-8").replace("=", "")
                    if encoding != "":
                        filename += "-" + encoding
                    path = "resources/" + filename

                    file = open("www/" + path, "wb")
                    file.write(data_encoding)
                    file.close()

                    location = "FILESYSTEM"
                    data_encoding = path

                database.execute('''
                    INSERT INTO encodings (
                        uri,
                        encoding,
                        location,
                        data,
                        length
                    )
                    VALUES (?, ?, ?, ?, ?)
                ''', (uri, encoding, location, data_encoding, length_data))

            tasks = []

            if encoded:
                for encoding in ENCODERS_ENCODING.keys():
                    tasks.append((PTask(encode, (data, encoding)), encoding))
            
            insert_encoding(data, "")

            for task, encoding in tasks:
                data_encoding = task.wait()

                # No point if the compressed data is bigger than the original.
                if len(data_encoding) < len(data):
                    insert_encoding(data_encoding, encoding)

            return uri

        ## Inserts an asset into the database.
        def insert_asset(id, data, type, cache, uri="", encoded=True):
            lock.acquire()

            if id in assets:
                raise RuntimeError("Duplicate id: " + id)
            
            uri = insert_resource(data, type, cache, uri, encoded)

            assets[id] = uri

            # Track the URI's history.
            history_assets[uri] = id

            lock.release()
        
            return uri
        
        tasks_renders = {}

        ## Inserts the given image as a series of graphic assets into the
        ## database.
        def insert_graphic(path, quality):
            id = os.path.relpath(path).replace("\\", "/")

            data = data_file(path)

            revision_graphic = astropy.time.Time(os.path.getmtime(path), format="unix")
            revision_graphic.format = "unix_tai"
            revision_graphic = float(str(revision_graphic))

            formats = []

            for type, qualities in QUALITIES_GRAPHIC.items():
                if quality in qualities:
                    formats.append((type, quality))
                # Very high quality is not supported by all lossy formats; use
                # high quality instead.
                elif quality == "VERY HIGH" and "HIGH" in qualities:
                    formats.append((type, "HIGH"))

            # TODO consider the image's actual width and never attempt to exceed
            # it.
            steps = math.floor(WIDTH_MAXIMUM_GRAPHIC / STEP_WIDTH_GRAPHIC)

            tasks = []
            assets_graphic = {}

            for type, quality in formats:
                for index_step in range(steps):
                    width = (index_step + 1) * STEP_WIDTH_GRAPHIC

                    id_asset = id + ";" + type + ";" + str(width) + ";" + quality

                    lock.acquire()

                    if id_asset in tasks_renders:
                        def run(id_asset):
                            return tasks_renders[id_asset].wait()

                        tasks.append((
                            NTask(run, (id_asset,)),
                            id_asset,
                            type,
                            width
                        ))
                    else:
                        def run(id_asset, data, type, width, quality):
                            # Check if the asset needs updating. Pull from the
                            # asset cache if not.
                            if id_asset in data_assets \
                            and revision_graphic < data_assets[id_asset]["revision"]:
                                data_conversion = data_file(data_assets[id_asset]["path"])
                            else:
                                data_conversion = PTask(
                                    render_image,
                                    (data, type, width, quality)
                                ).wait()

                                filename_data_asset = base64.b32encode(id_asset.encode("UTF-8")).decode("UTF-8").replace("=", "")
                                path_data_asset = "msssg/assets/" + filename_data_asset

                                file_data_asset = open(path_data_asset, "wb")
                                file_data_asset.write(data_conversion)
                                file_data_asset.close()

                                data_assets[id_asset] = {
                                    "path": path_data_asset,
                                    "revision": revision,
                                }

                            # TODO perhaps we may want to encode images?
                            # Probably worth attempting only for PNGs and JPEGs.
                            return (
                                NTask(
                                    insert_asset,
                                    (id_asset, data_conversion, type, "INDEFINITE", "", False)
                                ).wait(),
                                len(data_conversion)
                            )

                        task = NTask(run, (id_asset, data, type, width, quality))

                        tasks_renders[id_asset] = task
                        tasks.append((task, id_asset, type, width))
                    
                    lock.release()

            for task, id_asset, type, width in tasks:
                if type not in assets_graphic:
                    assets_graphic[type] = {}
                
                assets_graphic[type][width] = task.wait()

            return assets_graphic

        ## Inserts a file as an asset into the database.
        def insert_file(path, type, cache, uri=""):
            id = os.path.relpath(path).replace("\\", "/")

            if id in assets:
                if uri != "" and uri != assets[id]:
                    raise RuntimeError("Duplicate URIs for asset")

                return assets[id]

            # TODO is this something I'm willing to commit to?
            assert type != ""

            # TODO parse charset?

            match type:
                # HTML.
                case "application/msssg+xml;charset=UTF-8":
                    ## Returns a CSS selector for the current HTML document.
                    def select(selector):
                        return cssselect.CSSSelector(
                            selector,
                            namespaces={
                                "xhtml": "http://www.w3.org/1999/xhtml",
                                "msssg": "http://localhost/msssg"
                            }
                        )

                    directory = os.path.dirname(path)

                    document = xml.parse(path)

                    tasks_assets = []

                    # Replace asset attributes with their generated URIs.
                    for element in select("[msssg|asset]")(document):
                        attribute_subasset = element.attrib["{http://localhost/msssg}asset"]
                        type_subasset = element.attrib["{http://localhost/msssg}type"]

                        path_subasset = directory + "/" + element.attrib[attribute_subasset]

                        tasks_assets.append((
                            NTask(
                                insert_file,
                                (path_subasset, type_subasset, "INDEFINITE")
                            ),
                            element
                        ))

                    tasks_graphics = []
                    
                    # Process graphics.
                    # TODO implement other qualities
                    for element_picture in select("xhtml|picture[msssg|type=\"GRAPHIC\"]")(document):
                        quality = element_picture.attrib["{http://localhost/msssg}quality"]

                        element_img = None
                        for subelement in select("xhtml|img")(element_picture):
                            if element_img is None:
                                element_img = subelement
                            else:
                                raise RuntimeError("Multiple img in picture")
                            
                        if element_img is None:
                            raise RuntimeError("Missing img in picture")

                        for _ in select("xhtml|source")(element_picture):
                            raise RuntimeError("Use of source in picture is currently unsupported")

                        path_graphic = directory + "/" + element_img.attrib["src"]

                        tasks_graphics.append((
                            NTask(insert_graphic, (path_graphic, quality)),
                            element_picture,
                            element_img
                        ))

                    for task, element in tasks_assets:
                        uri_subasset = task.wait()

                        attribute_subasset = element.attrib.pop("{http://localhost/msssg}asset")
                        del element.attrib["{http://localhost/msssg}type"]

                        element.attrib[attribute_subasset] = uri_subasset

                    for task, element_picture, element_img in tasks_graphics:
                        assets_graphic = task.wait()

                        quality = element_picture.attrib.pop("{http://localhost/msssg}quality")
                        del element_picture.attrib["{http://localhost/msssg}type"]
                        del element_img.attrib["src"]
                        del element_img.attrib["srcset"]
                        sizes = element_img.attrib.pop("sizes")

                        # TODO sort types based on a metric that considers all
                        # sizes of a source. Do research into what this is.
                        types = sorted(assets_graphic.keys(),
                            key=lambda type: assets_graphic[type][WIDTH_FALLBACK_GRAPHIC][1]
                        )

                        for type in types:
                            assets_by_width = assets_graphic[type]
                            srcset = []

                            for width in sorted(assets_by_width.keys()):
                                asset = assets_by_width[width]

                                srcset.append(asset[0] + " " + str(width) + "w")
                            
                            element_source = element_picture.makeelement("source")
                            element_source.attrib["type"] = type
                            element_source.attrib["srcset"] = ", ".join(srcset)
                            element_source.attrib["sizes"] = sizes



                            # TODO testing
                            ss = []
                            for width in sorted(assets_by_width.keys()):
                                ss.append(str(assets_by_width[width][1]))
                            strss = "\n".join(ss)
                            element_source.attrib["data-lengths"] = base64.b64encode(strss.encode("UTF-8")).decode("UTF-8")




                            element_img.addprevious(element_source)
                        
                        # Set the fallback asset.
                        match quality:
                            case "LOSSLESS":
                                element_img.attrib["src"] = assets_graphic["image/png"][WIDTH_FALLBACK_GRAPHIC][0]
                            case _:
                                element_img.attrib["src"] = assets_graphic["image/jpeg"][WIDTH_FALLBACK_GRAPHIC][0]

                    xml.cleanup_namespaces(document)

                    # Sanity checks: make sure msssg namespace doesn't appear in
                    # the final HTML document.
                    for element in select("msssg|*")(document):
                        raise RuntimeError("Found tag in msssg namespace: " + element.tag)
                    for element in select("*")(document):
                        for attribute in element.attrib.keys():
                            if "{http://localhost/msssg}" in attribute:
                                raise RuntimeError("Found attribute in msssg namespace: " + attribute)

                    data = xml.tostring(document)
                    type = "application/xhtml+xml;charset=UTF-8"

                    # document = html.document_fromstring(data)

                    # for attribute in [
                    #     "xmlns",
                    #     "xml:lang",
                    # ]:
                    #     if attribute in document.attrib:
                    #         del document.attrib[attribute]
                        
                    # data = html.tostring(document, doctype="<!DOCTYPE html>")

                    # data = minify_html.minify(data.decode("UTF-8"),
                    #     minify_css=True,
                    # )
                    # data = data.encode("UTF-8")

                    # type = "text/html;charset=UTF-8"
                    #


                case _:
                    data = data_file(path)

            return insert_asset(id, data, type, cache, uri)



        






        


        # FOR STRESS TESTING

        # for index in range(9900, 10000, 1):
        #     links["/test/" + str(index + 1)] = {
        #         "action": "RESOURCE",
        #         # "path": "src/www/test.html",
        #         "path": "src/exwww/testk/" + str(index + 1),
        #         "type": "text/plain;charset=UTF-8",
        #         "cache": "SHORT",
        #     }
        # for path in [
        #     # "src/www/tiff.png",
        #     # "src/www/cherry.png",
        #     # "src/www/louise.png",
        #     # "src/www/lake.png",
        #     "src/www/about.html"
        # ]:
        #     data = b""
        #     file = open(path, "rb")
        #     while buffer := file.read():
        #         data += buffer
        #     file.close()

        #     insert_asset(path + ";source", data, "text/html", "INDEFINITE")
        #     # insert_image(data)
        


        




        tasks = []

        for uri, link in links.items():
            # Clear the URI's history.
            if uri in history_assets:
                del history_assets[uri]

            match link["action"]:
                # Serve a resource to the client.
                case "RESOURCE":
                    cache = "NONE" if not "cache" in link else link["cache"]

                    insert_file(link["path"], link["type"], cache, uri)
                
                # Serve a permanent URI to a resource to the client.
                case "PERMALINK":
                    cache = "NONE" if not "cache" in link else link["cache"]

                    if cache == "INDEFINITE":
                        raise RuntimeError("Illegal cache for permalink: INDEFINITE")
                    
                    insert_resource(data_file(link["path"]), link["type"], cache, uri)

                # Tell the client to redirect.
                case "REDIRECT":
                    database.execute('''
                        INSERT INTO uris (uri, action, cache)
                        VALUES (?, "REDIRECT", ?)
                    ''', (uri, link["cache"]))

                    database.execute('''
                        INSERT INTO redirects (uri, type, location)
                        VALUES (?, ?, ?)
                    ''', (uri, link["type"], link["location"]))
                
                case _:
                    raise RuntimeError("Unknown action: " + link["action"])

        for task in tasks:
            task.wait()

        pool.close()
        pool.join()

        for uri, id_asset in history_assets.items():
            # The asset is alive and well; redirect past URIs.
            if id_asset in assets:
                uri_asset = assets[id_asset]

                # Only redirect *past* URIs.
                if uri != uri_asset:
                    database.execute('''
                        INSERT INTO uris (uri, action, cache)
                        VALUES (?, "REDIRECT", "NONE")
                    ''', (uri,))
                    
                    database.execute('''
                        INSERT INTO redirects (uri, type, location)
                        VALUES (?, ?, ?)
                    ''', (uri, "PERMANENT", uri_asset))

            # The asset has been deleted; send `Gone` to client.
            else:
                database.execute('''
                    INSERT INTO uris (uri, action, cache)
                    VALUES (?, "DELETION", "NONE")
                ''', (uri,))

        database.execute('''
            PRAGMA optimize
        ''')

        database.backup(database_disk, sleep=0)
        database.close()
        database_disk.close()

        json.dump(
            history_assets,
            open("msssg/history_assets.json", "w"),
            indent=4,
            sort_keys=True
        )
        json.dump(
            data_assets,
            open("msssg/data_assets.json", "w"),
            indent=4,
            sort_keys=True
        )

        animator.terminate()

        duration = time.monotonic() - time_start
        print("\x1B[102;30m Build successful (" + "{:.3f}".format(duration) + " s) \x1B[0m")

        sys.exit(0)

    except KeyboardInterrupt:
        pool.terminate()
        pool.join()

        animator.terminate()

        print("\x1B[107;30m Build cancelled by user \x1B[0m")

        sys.exit(1)
    
    except Exception as exception:
        pool.terminate()
        pool.join()

        animator.terminate()

        for line in traceback.format_exception(exception):
            print("\x1B[91m" + line + "\x1B[0m", end="")

        print("\x1B[41;97m Build failed \x1B[0m")

        sys.exit(1)

if __name__ == "__main__":
    main()