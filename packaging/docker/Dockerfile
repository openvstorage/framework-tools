# Download base image ubuntu 16.04
FROM ubuntu:16.04

# Update Ubuntu Software repository
RUN apt-get update \
    && apt-get install -y --force-yes \
        rsyslog \
        sudo \
        openssl \
        python-pip \
        dpkg-dev

# Install requirements for converting pip to debian-packages
RUN pip install py2deb
