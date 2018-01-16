FROM python:3.6-alpine

RUN apk add --update --no-cache bash gettext build-base
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PIP_DISABLE_PIP_VERSION_CHECK=1
ENV LANG=C.UTF-8

CMD ["python", "slappd.py"]
WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY . ./
