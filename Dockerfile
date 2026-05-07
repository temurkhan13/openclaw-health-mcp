# Dockerfile — openclaw-health-mcp
#
# Build: docker build -t openclaw-health-mcp .
# Run:   docker run -i openclaw-health-mcp
#
# The MCP server speaks stdio JSON-RPC. Pipe MCP messages on stdin; receive responses on stdout.
# Uses psutil for system metrics; works inside containers but reflects the container's view of resources.

FROM python:3.12-slim

WORKDIR /app

COPY pyproject.toml README.md LICENSE ./
COPY src/ ./src/

RUN pip install --no-cache-dir .

ENTRYPOINT ["openclaw-health-mcp"]
