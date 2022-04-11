<?php

// // Convert PHP errors into equivalent exceptions.
// set_error_handler(
// 	function($level, $message, $file, $line) {
// 		throw new ErrorException($message, -1, $level, $file, $line);;
// 	},
// 	E_ALL | E_DEPRECATED | E_USER_DEPRECATED
// );

// For developing purposes. This is **NOT SECURE**, but since it's only purpose
// is to prevent someone from accidentally wandering onto this site before it's
// done, it's good enough.
if (!isset($_SERVER["HTTP_AUTHORIZATION"])
|| $_SERVER["HTTP_AUTHORIZATION"] !== "Basic " . base64_encode("username:password")) {
    http_response_code(401);
    header("WWW-Authenticate: basic");
    exit();
}






// TODO handle GET arguments?

$database = new SQLite3("database.db", SQLITE3_OPEN_READONLY);

// Get the request URI.
$uri = parse_url($_SERVER["REQUEST_URI"], PHP_URL_PATH);

// Get the request etag.
$etags = [];
if (isset($_SERVER["HTTP_IF_NONE_MATCH"])) {
    foreach (array_map("trim", explode(",", $_SERVER["HTTP_IF_NONE_MATCH"]))
    as $etag) {
        $etags[$etag] = null;
    }
}
$etag = sizeof($etags) === 1 ? array_key_first($etags) : "";

// Get the request encoding.
$encodings = ["" => null];
if (isset($_SERVER["HTTP_ACCEPT_ENCODING"])) {
    $headerEncodings = strtolower($_SERVER["HTTP_ACCEPT_ENCODING"]);
    $headerEncodings = str_replace(" ", "", $headerEncodings);

    foreach (explode(",", $headerEncodings) as $headerEncoding) {
        // Completely ignore the client's quality desires and impose our own.
        $encoding = strstr($headerEncoding, ";q=", true);
        if ($encoding === false) {
            $encoding = $headerEncoding;
        }

        $encodings[$encoding] = null;
    }
}
$encodings = array_keys($encodings);

$t = microtime(true);

$query = $database->prepare('
    SELECT
        uris.uri AS uri,
        uris.action AS action,
        cache,
        resources.type AS typeResource,
        etag,
        encoding,
        encodings.location AS locationData,
        CASE WHEN etag = ? THEN NULL ELSE data END data,
        length,
        redirects.type AS typeRedirect,
        redirects.location AS locationRedirect
    FROM
        uris
        LEFT JOIN resources ON uris.uri = resources.uri
        LEFT JOIN encodings ON uris.uri = encodings.uri
        LEFT JOIN redirects ON uris.uri = redirects.uri
    WHERE
        uris.uri IN (?, "~notfound")
        AND (
            encoding IN (' . implode(",", array_fill(0, sizeof($encodings), "?")) . ')
            OR encoding IS NULL
        )
    ORDER BY
        uris.uri,
        length
    LIMIT 1
');

$query->bindValue(1, $etag);
$query->bindValue(2, $uri);
foreach ($encodings as $index => $encoding) {
    $query->bindValue(3 + $index, $encoding);
}

$result = $query->execute();

$row = $result->fetchArray(SQLITE3_ASSOC);

$result->finalize();
$query->close();




header("Server-Timing: query;dur=" . number_format((microtime(true) - $t) * 1000, 3, ".", ""));




assert($row !== false);

if ($row["cache"] !== "NONE") {
    switch ($row["cache"]) {
        case "INSTANT":
            header("Cache-Control: public, no-cache");
            break;
        
        case "SHORT":
            header("Cache-Control: public, max-age=100"); // 1.7 minutes.
            break;

        case "MEDIUM":
            header("Cache-Control: public, max-age=10000"); // 2.8 hours.
            break;
        
        case "LONG":
            header("Cache-Control: public, max-age=1000000"); // 11.6 days.
            break;

        case "INDEFINITE":
            header("Cache-Control: public, max-age=31536000, immutable");
            break;
        
        default:
            throw new RuntimeException("Unknown cache: " . $row["cache"]);
    }
}

switch ($row["action"]) {
    case "RESOURCE":
        if ($row["cache"] !== "NONE") {
            header("Vary: Accept-Encoding");

            // Never send an etag with a 404.
            if ($row["uri"] !== "~notfound") {
                header("ETag: " . $row["etag"]);
            }
        }

        // Client's cache was validated. 
        if (is_null($row["data"])) {
            // Since we never send etags with 404s, we will never accidentally
            // send a 304 instead of a 404.
            http_response_code(304);
        }
        // Serve the file.
        else {
            http_response_code($row["uri"] === "~notfound" ? 404 : 200);

            // Assert that `$row["typeResource"] === "")` implies
            // `$row["length"] === 0`.
            assert(!($row["typeResource"] === "") | $row["length"] === 0);
            
            header("Content-Type: " . $row["typeResource"]);

            if ($row["encoding"] !== "") {
                header("Content-Encoding: " . $row["encoding"]);
            }

            header("Content-Length: " . $row["length"]);

            switch ($row["locationData"]) {
                case "DATABASE":
                    echo $row["data"];
                    break;
                
                case "FILESYSTEM":
                    readfile($row["data"]);
                    break;
                
                default:
                    throw new RuntimeException("Unknown resource location: " . $row["locationData"]);
            }
        }

        break;

    case "REDIRECT":
        switch ($row["typeRedirect"]) {
            case "TEMPORARY":
                http_response_code(302);
                break;
            
            case "PERMANENT":
                http_response_code(301);
                break;
            
            default:
                throw new RuntimeException("Unknown redirect duration: " . $row["typeRedirect"]);
        }

        header("Location: " . $row["locationRedirect"]);

        break;
    
    case "DELETION":
        http_response_code(410);
        break;

    default:
        throw new RuntimeException("Unknown URI action: " . $row["action"]);
}

$database->close();