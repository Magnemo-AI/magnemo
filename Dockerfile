# Magnemo — governed memory for AI agents. MCP server over stdio.
# Zero network calls at runtime: the only network use is this build's pip install.
# Run:  docker run -i --rm --network none -v /path/to/vault:/vault magnemo
FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1
RUN pip install --no-cache-dir magnemo-mcp==0.6.2
ENV MAGNEMO_VAULT=/vault MAGNEMO_AGENT=agent
VOLUME ["/vault"]
ENTRYPOINT ["magnemo-mcp"]
