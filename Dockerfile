FROM docker.io/node:20-alpine AS builder
ARG QUARTZ_VERSION="v4.4.0"
RUN apk add --no-cache git

WORKDIR /usr/src/app/
RUN git clone --depth 1 --branch ${QUARTZ_VERSION} \
    -- "https://github.com/jackyzha0/quartz.git" ./


FROM docker.io/node:20-slim
COPY --from=builder /usr/src/app/ /usr/src/app/
WORKDIR /usr/src/app/
RUN rm -r ./content/

## if package.json and/or package-lock.json are to be overriden
## in ./quartz/, they must be copied before running `npm ci`
# COPY ./quartz/package.json ./quartz/package-lock.json .
RUN npm ci

COPY ./quartz/ ./

CMD ["npx", "quartz", "build", "--serve"]
