FROM python:3.11-slim
WORKDIR /app

# Install matrix shared library
COPY ../../setup.py /tmp/biowerk-setup.py
COPY ../../matrix /tmp/matrix
COPY ../../requirements.txt /tmp/requirements.txt
RUN pip install -r /tmp/requirements.txt && \
    cd /tmp && pip install -e . && \
    rm -rf /tmp/*

# Copy service files
COPY . .
COPY ../../schemas ./schemas

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8002"]
