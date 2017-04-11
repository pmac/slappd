FROM mozmeao/base:python-3.6-alpine

CMD ["python", "slappd.py"]
WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY . ./
