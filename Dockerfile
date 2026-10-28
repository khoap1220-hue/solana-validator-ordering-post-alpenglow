FROM python:3.11-slim

WORKDIR /workspace
COPY . /workspace

ENV PYTHONUNBUFFERED=1
ENV SOLANA_RPC_URL="https://api.mainnet-beta.solana.com"
ENV DRY_RUN_DEFAULT="true"
ENV MAX_SPEND_LAMPORTS="50000000"

CMD ["python", "-m", "unittest", "discover", "-s", "tests", "-v"]
