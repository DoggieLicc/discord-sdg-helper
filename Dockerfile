# "Building" the venv
FROM dhi.io/python:3.10-alpine3.22-dev AS build-stage

ENV PYTHONUNBUFFERED=1
ENV PATH="/app/venv/bin:$PATH"

WORKDIR /app

RUN apk --no-interactive -U add git && apk cache clean

RUN python -m venv /app/venv

COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

# Runtime stage
FROM dhi.io/python:3.10-alpine3.22 AS runtime-stage

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PATH="/app/venv/bin:$PATH"

WORKDIR /app

COPY --from=build-stage /app/venv /app/venv

COPY . /app

CMD ["python", "main.py"]
