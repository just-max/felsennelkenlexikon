#!/usr/bin/env bash

set -e

# TODO: allow overriding

SRC_DIR="src/"
BUILD_DIR="build/"

CONTAINER_TAG="localhost/fnl-quartz:latest"

CONTAINER_CMD=podman

content_build() {
    local definitions_dir="$BUILD_DIR"/definitions/
    mkdir -p "$BUILD_DIR"/content/ "$definitions_dir"
    cp -rT "$SRC_DIR"/content/ "$BUILD_DIR"/content/
    python "$SRC_DIR"/parser.py \
        --input-html "$SRC_DIR"/lexikon.html \
        --output-parsed-html "$definitions_dir"/lexikon-cleaned.html \
        --output-parsed-jsonl "$definitions_dir"/lexikon-cleaned.jsonl \
        --output-parsed-definitions "$definitions_dir"/lexikon-defs.json \
        "$BUILD_DIR"/content/
}

container_build() {
    # TODO: move context to build directory
    "$CONTAINER_CMD" build . --tag "$CONTAINER_TAG"
}

container_run() {
    "$CONTAINER_CMD" run --rm --interactive --tty \
        --publish 8080:8080 \
        --security-opt label=disable \
        --mount type=bind,src="$BUILD_DIR"/content/,dst=/usr/src/app/content/,ro=true \
        "$CONTAINER_TAG"
}

lexikon_fetch() {
    curl -o "$SRC_DIR"/lexikon.html \
        'https://web.archive.org/web/20161021102523/http://felsennelkenanger.de/lexikon/'
}

clean() {
    rm -rf "$BUILD_DIR"
}

"$@"
