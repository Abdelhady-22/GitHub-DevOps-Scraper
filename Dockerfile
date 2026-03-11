FROM python:3.12-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source code
COPY *.py ./
COPY scraper_config.yaml .

# Create output directories
RUN mkdir -p raw staging processed logs

# tokens.txt and .env should be mounted at runtime
# docker run -v ./tokens.txt:/app/tokens.txt ...

ENTRYPOINT ["python", "run_all.py"]
