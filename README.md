# Masha's Somewhat Static Site Generator

A somewhat static site generator built for my friend Masha.

It only works on Windows, so if you don't have that, sorry. Maybe in the future.
You'll also need Python 3.10 (CPython) and a bunch of pip libraries. If you want
to run the test server, you'll also need PHP.

## Commands

```msssg clean```

Deletes any existing builds. This will also delete any revision history, so try
not to run this too often.

```msssg build```

Builds the site. The produced site is heavily optimized for runtime performance
at the extreme expense of "build-time" performance, so expect to sit around for
a little while. Read a manga or make a coffee or something.

```msssg run```

Runs a previously built site using PHP's built-in test server.

```msssg buildrun```


Runs `msssg build` immediately followed by `msssg run`.
