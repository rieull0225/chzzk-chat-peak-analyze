FROM python:3.11-slim

# Install system dependencies
RUN apt-get update && apt-get install -y \
    git \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy project files
COPY pyproject.toml README.md ./
COPY nokchart ./nokchart

# Install package
RUN pip install --no-cache-dir -e .

# Create output directory
RUN mkdir -p /app/output

# Set environment variables
ENV PYTHONUNBUFFERED=1

# Default command
CMD ["nokchart", "watch", "--channels", "/app/channels.yaml", "--config", "/app/config.yaml"]
