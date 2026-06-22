# Margadrishti backend image — shared by api / worker / scheduler process types.
FROM python:3.11-slim

# Geo stack (geopandas/pyogrio/shapely) ships wheels; build-essential covers the rest.
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app
# Copy the package BEFORE install — hatchling needs margadrishti/ to exist to build the wheel.
COPY pyproject.toml ./
COPY margadrishti ./margadrishti
RUN pip install --no-cache-dir .
COPY tests ./tests

ENV PYTHONUNBUFFERED=1 MARGA_DATA_ROOT=/app/data
EXPOSE 8000

# Default to the API; worker/scheduler override `command` in compose.
CMD ["uvicorn", "margadrishti.api.app:app", "--host", "0.0.0.0", "--port", "8000"]
