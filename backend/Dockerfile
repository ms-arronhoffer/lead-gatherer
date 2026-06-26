FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
# Install the Chromium browser used by the optional LinkedIn enrichment feature
# (Playwright). --with-deps pulls the required system libraries.
RUN playwright install --with-deps chromium
COPY . .
