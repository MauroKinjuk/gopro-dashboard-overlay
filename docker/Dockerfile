FROM ubuntu:24.04

LABEL maintainer="GoPro Overlay Dashboards <gopro-overlay@time4tea.net>"
ENV PATH=$PATH:/usr/bin


RUN apt update && apt install -y curl gnupg unzip fonts-noto fonts-roboto ffmpeg sudo libcairo-dev software-properties-common
RUN add-apt-repository -y ppa:deadsnakes/ppa
RUN apt install -y python3.14 python3.14-venv

WORKDIR /
RUN python3.14 -mvenv venv
RUN /venv/bin/python3.14 -m pip install --upgrade pip

RUN apt install -y gcc
RUN apt install -y python3.14-dev libcairo2-dev pkg-config

RUN apt install -y libnvidia-decode-580-server libnvidia-encode-580-server
ARG GOPRO_OVERLAY_VERSION
RUN /venv/bin/pip install "gopro-overlay[cairo]==${GOPRO_OVERLAY_VERSION}"

VOLUME /work
WORKDIR /work

COPY entrypoint.sh /

ENTRYPOINT [ "/entrypoint.sh" ]

