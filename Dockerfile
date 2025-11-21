FROM ubuntu:24.04

RUN apt update && \
  DEBIAN_FRONTEND=noninteractive apt install -y \
  build-essential \
  python3-dev \
  python3-pip \
  python-gi-dev \
  python3-numpy \
  python3-urllib3 \
  wget \
  vim-tiny \
  meson



RUN apt update && \
  DEBIAN_FRONTEND=noninteractive apt install -y \
  gstreamer1.0-tools \
  gstreamer1.0-plugins-base \
  gstreamer1.0-plugins-good \
  gstreamer1.0-plugins-bad \
  gstreamer1.0-plugins-ugly \
  gstreamer1.0-libav \
  libgstreamer1.0-0 \
  libgstreamer1.0-dev \
  libgstreamer-plugins-base1.0-dev


WORKDIR /root
RUN GSTREAMER_VERSION=$(gst-launch-1.0 --version | grep version | tr -s ' ' '\n' | tail -1) \
    && wget https://gstreamer.freedesktop.org/src/gst-python/gst-python-$GSTREAMER_VERSION.tar.xz --no-check-certificate \
    && tar -xJf gst-python-$GSTREAMER_VERSION.tar.xz \
    && rm gst-python-$GSTREAMER_VERSION.tar.xz \
    && cd gst-python-$GSTREAMER_VERSION \
    && PREFIX=$(dirname $(dirname $(which python3))) \
    && meson build --prefix=$PREFIX \
    && ninja -C build \
    && ninja -C build install \
    && mv $(dirname $(find /usr -name "libgstpython.so")) /usr/local/lib

WORKDIR /src 
ENV GST_PLUGIN_PATH=/usr/local/lib/gstreamer-1.0/

RUN apt update && \
  DEBIAN_FRONTEND=noninteractive apt install -y \
  python3-opencv \
  opencv-data

# Copy application files
COPY *.py /src/

ENV CONFIG_EXTERNAL=""
CMD ["python3", "main.py"]
