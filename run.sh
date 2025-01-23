#!/usr/bin/env bash

set -e

SRC_DIR="src/"
BUILD_DIR="build/"

CONTAINER_IMG=${CONTAINER_IMG:-localhost/fnl-quartz:latest}
CONTAINER_CMD=${CONTAINER_CMD:-podman}

content_build() {
    local definitions_dir="$BUILD_DIR"/definitions/
    mkdir -p "$BUILD_DIR"/content/ "$definitions_dir"
    python "$SRC_DIR"/parser.py \
        --input-html "$SRC_DIR"/lexikon.html \
        --output-parsed-html "$definitions_dir"/lexikon-cleaned.html \
        --output-parsed-jsonl "$definitions_dir"/lexikon-cleaned.jsonl \
        --output-parsed-definitions "$definitions_dir"/lexikon-defs.json \
        "$BUILD_DIR"/content/
    cp -rT "$SRC_DIR"/content/ "$BUILD_DIR"/content/
}

container_build() {
    # TODO: move context to build directory
    "$CONTAINER_CMD" build . --tag "$CONTAINER_IMG"
}

container_run() {
    # use `--security-opt label=disable` to disable SELinux protections,
    # otherwise mounts break (TODO: does this interfere with non-SELinux systems?)
    mkdir -p "$BUILD_DIR"/content/ "$BUILD_DIR"/public/
    "$CONTAINER_CMD" run --rm --interactive --tty \
        --security-opt label=disable \
        --mount type=bind,src="$BUILD_DIR"/content/,dst=/usr/src/app/content/,ro=true \
        --mount type=bind,src="$BUILD_DIR"/public/,dst=/usr/src/app/public/ \
        "$CONTAINER_IMG" \
        "$@"
}

container_serve() {
    mkdir -p "$BUILD_DIR"/content/
    "$CONTAINER_CMD" run --rm --interactive --tty \
        --security-opt label=disable \
        --mount type=bind,src="$BUILD_DIR"/content/,dst=/usr/src/app/content/,ro=true \
        --publish 8080:8080 \
        --publish 3001:3001 \
        "$CONTAINER_IMG" \
        npx quartz build --serve
}

lexikon_fetch() {
    curl -o "$SRC_DIR"/lexikon.html \
        'https://web.archive.org/web/20161021102523/http://felsennelkenanger.de/lexikon/'
}

clean() {
    rm -rf "$BUILD_DIR"
}

"$@"
