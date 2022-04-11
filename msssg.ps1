$command = $args[0]

function Run-Server {
    Push-Location www
    try {
        php -S localhost:80 ../src/server.php
    }
    finally {
        Pop-Location
    }
}

Switch ($command) {
    "clean" {
        rm -Force -Recurse -ErrorAction SilentlyContinue www
        rm -Force -Recurse -ErrorAction SilentlyContinue msssg
    }
    "build" {
        py src/builder.py
    }
    "run" {
        if (!(Test-Path www)) {
            py src/builder.py

            if ($LASTEXITCODE -eq 0) {
                Run-Server
            }
        }
        else {
            Run-Server
        }
    }
    "buildrun" {
        py src/builder.py

        if ($LASTEXITCODE -eq 0) {
            Run-Server
        }
    }
    default {
        echo "Unknown command: $command"
    }
}