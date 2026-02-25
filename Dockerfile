# Optional containerized run for Automaton Auditor.
# Build: docker build -t automaton-auditor .
# Run: docker run --env-file .env -v $(pwd)/audit:/app/audit -v $(pwd)/report.pdf:/app/report.pdf automaton-auditor <repo_url> /app/report.pdf --output /app/audit/report.md

FROM python:3.11-slim

WORKDIR /app

# Install uv and dependencies (lockfile for reproducible build)
COPY pyproject.toml uv.lock ./
RUN pip install --no-cache-dir uv && uv sync --no-install-project
COPY . .
RUN uv sync

# Default: run CLI with args
ENTRYPOINT ["uv", "run", "python", "-m", "src.run"]
CMD ["https://github.com/octocat/Hello-World", "/app/report.pdf", "--output", "/app/audit/report.md"]
