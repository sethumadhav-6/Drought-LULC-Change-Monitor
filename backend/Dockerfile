# Canopy GeoAI backend -- deployable to Render (or any container host).
FROM python:3.11-slim

# GDAL/GEOS/PROJ + cartopy's build deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential gdal-bin libgdal-dev libgeos-dev libproj-dev \
    proj-data proj-bin libspatialindex-dev ffmpeg \
    && rm -rf /var/lib/apt/lists/*

ENV GDAL_CONFIG=/usr/bin/gdal-config

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

ENV PORT=8000
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
