FROM python:3.12-slim

# Apply Debian security updates the published base image does not carry yet.
# The base image is rebuilt on Docker Hub's schedule, not Debian's, so a fix
# released after the last base rebuild (e.g. apt 3.0.3 -> 3.0.4 for
# CVE-2026-109518, libpcre2 10.46-1deb13u3 for CVE-2026-103111) would
# otherwise ship in this image and fail the Trivy CRITICAL,HIGH gate in
# .github/workflows/security.yml. Upgrading the packages already installed
# (nothing new, package lists removed) makes every build carry the Debian
# fixes available at build time.
RUN apt-get update \
    && apt-get upgrade -y \
    && rm -rf /var/lib/apt/lists/*

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8000

WORKDIR /app

COPY requirements.txt .
COPY constraints/requirements-py312.txt ./constraints.txt
RUN pip install --no-cache-dir -c constraints.txt -r requirements.txt

# The packaged web shell lives under chaoshire/web, not at the repository root.
COPY backend.py ./
COPY chaoshire ./chaoshire

RUN useradd --create-home --uid 10001 chaoshire \
    && mkdir -p /app/data \
    && chown -R chaoshire:chaoshire /app/data
USER chaoshire

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
    CMD python -c "import os, urllib.request; urllib.request.urlopen('http://127.0.0.1:' + os.environ.get('PORT', '8000') + '/api/ready', timeout=2)"

CMD ["sh", "-c", "python -m uvicorn backend:app --host 0.0.0.0 --port ${PORT}"]
