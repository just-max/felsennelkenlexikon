#!/usr/bin/env bash

set -e

# TODO: allow overriding
# rename Dockerfile to Containerfile or something

SRC_DIR="src/"
CONTENT_INPUT="$SRC_DIR"/content/

BUILD_DIR="build/"
CONTENT_DIR="$BUILD_DIR"/content/
DEFINITIONS_DIR="$BUILD_DIR"/definitions/

CONTAINER_TAG="localhost/fnl-quartz:latest"

CONTAINER_CMD=podman

content_build() {
    mkdir -p "$CONTENT_DIR" "$DEFINITIONS_DIR"
    cp -rT "$CONTENT_INPUT" "$CONTENT_DIR"
    python "$SRC_DIR"/parser.py \
        --input-html "$SRC_DIR"/lexikon.html \
        --output-parsed-html "$DEFINITIONS_DIR"/lexikon-cleaned.html \
        --output-parsed-jsonl "$DEFINITIONS_DIR"/lexikon-cleaned.jsonl \
        --output-parsed-definitions "$DEFINITIONS_DIR"/lexikon-defs.json \
        "$BUILD_DIR"/content/
}

container_build() {
    content_build

    # TODO: move context to build directory
    "$CONTAINER_CMD" build . --tag "$CONTAINER_TAG" "$BUILD_DIR"
}

container_run() {
    "$CONTAINER_CMD" run --rm --interactive --tty \
        --publish 8080:8080 \
        --security-opt label=disable \
        --mount type=bind,src="$BUILD_DIR"/content/,dst=/usr/src/app/content/,ro=true \
        "$CONTAINER_TAG"
}

lexikon_fetch() {
    curl -o "$LEXIKON_INPUT" \
        'https://web.archive.org/web/20161021102523/http://felsennelkenanger.de/lexikon/'
}

clean() {
    rm -rf "$BUILD_DIR"
}

"$@"
