FROM quay.io/mozmar/base:latest

# Set Python-related environment variables to reduce annoying-ness
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
ENV PIP_DISABLE_PIP_VERSION_CHECK=1
ENV LANG=C.UTF-8

CMD ["python3", "slappd.py"]
WORKDIR /app
RUN update-alternatives --install /bin/sh sh /bin/bash 10

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
                    build-essential python3-{dev,pip,setuptools} && \
    rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./
RUN pip3 install --no-cache-dir -r requirements.txt

COPY slappd.py ./
