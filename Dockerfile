FROM alpine as builder

ARG TARGETPLATFORM

RUN if [ "$TARGETPLATFORM" = "linux/amd64" ]; then \
        wget https://github.com/james58899/hath-rust/releases/latest/download/hath-rust-x86_64-unknown-linux-gnu -O /tmp/hath-rust; \
    elif [ "$TARGETPLATFORM" = "linux/arm/v7" ]; then \
        wget https://github.com/james58899/hath-rust/releases/latest/download/hath-rust-armv7-unknown-linux-gnueabihf -O /tmp/hath-rust; \
    fi


FROM python:slim

WORKDIR /hath

COPY --from=builder /tmp/hath-rust .
COPY . .

RUN chmod a+x hath-rust \
    && chmod a+x natter.py \
    && chmod a+x main.py \
    && pip3 install --no-cache-dir -r requirements.txt

ENTRYPOINT ["/hath/main.py"]
