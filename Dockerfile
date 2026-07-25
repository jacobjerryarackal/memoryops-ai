# ============================================================
# Stage 1: Build dependencies
# ============================================================
FROM python:3.11-slim AS builder

WORKDIR /build

COPY requirements.txt .

# Install dependencies to a local user directory for caching
RUN pip install --no-cache-dir --user -r requirements.txt

# ============================================================
# Stage 2: Production runtime image
# ============================================================
FROM python:3.11-slim AS runner

WORKDIR /workspace

# Copy installed libraries from builder stage
COPY --from=builder /root/.local /root/.local

# Copy the rest of the application
COPY . /workspace

# Ensure dependencies and scripts are available in paths
ENV PATH=/root/.local/bin:$PATH
ENV PYTHONPATH=/workspace/services/api

EXPOSE 8000

# Run FastAPI application
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
