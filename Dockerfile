FROM alpine as builder

ARG TARGETPLATFORM

RUN if [ "$TARGETPLATFORM" = "linux/amd64" ]; then \
        wget https://github.com/james58899/hath-rust/releases/download/v1.3.0/hath-rust-x86_64-unknown-linux-gnu -O /tmp/hath-rust; \
    elif [ "$TARGETPLATFORM" = "linux/arm/v7" ]; then \
        wget https://github.com/james58899/hath-rust/releases/download/v1.3.0/hath-rust-armv7-unknown-linux-gnueabihf -O /tmp/hath-rust; \
    fi


FROM python:slim

COPY --from=builder /tmp/hath-rust /opt/hath-rust
COPY main.py /opt/main.py
COPY natter.py /opt/natter.py

RUN chmod a+x /opt/hath-rust \
    && chmod a+x /opt/natter.py \
    && chmod a+x /opt/main.py \
    && pip3 install pyyaml httpx

WORKDIR /hath

ENTRYPOINT ["/opt/main.py"]
