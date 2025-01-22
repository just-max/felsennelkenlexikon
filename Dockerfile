FROM docker.io/node:20-alpine AS builder
ARG QUARTZ_VERSION="v4.4.0"
RUN apk add --no-cache git

WORKDIR /usr/src/app/
RUN git clone --depth 1 --branch ${QUARTZ_VERSION} \
    -- "https://github.com/jackyzha0/quartz.git" ./

RUN rm -r ./content/
COPY ./quartz/ ./
RUN npm ci

COPY ./content/ ./content/

CMD ["npx", "quartz", "build", "--serve"]
