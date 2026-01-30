# Agentic Search Audit Dockerfile
# Multi-stage build for optimized image size

# ============================================
# Stage 1: Builder - Install dependencies
# ============================================
FROM python:3.11-slim AS builder

WORKDIR /app

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Create virtual environment
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Copy dependency files
COPY pyproject.toml setup.py ./
COPY src/ ./src/

# Install Python dependencies
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -e ".[dev]"


# ============================================
# Stage 2: Runtime - Minimal production image
# ============================================
FROM python:3.11-slim AS runtime

# Install runtime dependencies: Chrome, Node.js, and system libs
RUN apt-get update && apt-get install -y --no-install-recommends \
    # Chrome dependencies
    wget \
    gnupg2 \
    ca-certificates \
    fonts-liberation \
    libasound2 \
    libatk-bridge2.0-0 \
    libatk1.0-0 \
    libatspi2.0-0 \
    libcups2 \
    libdbus-1-3 \
    libdrm2 \
    libgbm1 \
    libgtk-3-0 \
    libnspr4 \
    libnss3 \
    libxcomposite1 \
    libxdamage1 \
    libxfixes3 \
    libxkbcommon0 \
    libxrandr2 \
    xdg-utils \
    # Node.js
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install Google Chrome
RUN wget -q -O - https://dl-ssl.google.com/linux/linux_signing_key.pub | gpg --dearmor -o /usr/share/keyrings/googlechrome-linux-keyring.gpg && \
    echo "deb [arch=amd64 signed-by=/usr/share/keyrings/googlechrome-linux-keyring.gpg] http://dl.google.com/linux/chrome/deb/ stable main" > /etc/apt/sources.list.d/google-chrome.list && \
    apt-get update && \
    apt-get install -y --no-install-recommends google-chrome-stable && \
    rm -rf /var/lib/apt/lists/*

# Install Node.js (for chrome-devtools-mcp)
RUN curl -fsSL https://deb.nodesource.com/setup_20.x | bash - && \
    apt-get install -y nodejs && \
    rm -rf /var/lib/apt/lists/*

# Install chrome-devtools-mcp globally
RUN npm install -g @anthropic/chrome-devtools-mcp

# Create non-root user for security
RUN useradd -m -u 1000 -s /bin/bash auditor && \
    mkdir -p /app /home/auditor/.cache && \
    chown -R auditor:auditor /app /home/auditor

# Copy virtual environment from builder
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Copy application code
WORKDIR /app
COPY --chown=auditor:auditor . .

# Switch to non-root user
USER auditor

# Set Chrome to run in sandbox-less mode (required for containers)
ENV CHROME_FLAGS="--no-sandbox --disable-setuid-sandbox --disable-dev-shm-usage"

# Set default output directory
ENV AUDIT_OUTPUT_DIR="/app/runs"

# Create runs directory
RUN mkdir -p /app/runs

# Expose port for potential web interface
EXPOSE 8080

# Default command
ENTRYPOINT ["search-audit"]
CMD ["--help"]
