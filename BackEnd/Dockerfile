# La API y la ingesta usan Python 3.11 (arquitectura aprobada). El modelado usa 3.13, el entorno del Protocolo:
# XGBoost 3.4.1 (el que reproduce los resultados del asesor) exige Python >= 3.12.
ARG PYTHON=3.11
FROM python:${PYTHON}-slim
ARG REQUISITOS=requirements.txt
WORKDIR /app
COPY requirements*.txt ./
RUN pip install --no-cache-dir -r ${REQUISITOS}
COPY . .
# SERVICIO: api_plataforma | servicio_ingesta | servicio_modelado
ARG SERVICIO=api_plataforma
ENV SERVICIO=${SERVICIO}
RUN useradd -m app && mkdir -p /datos/csv && chown -R app /app /datos
USER app
CMD ["sh", "-c", "uvicorn ${SERVICIO}.main:app --host 0.0.0.0 --port ${PUERTO:-8000} --proxy-headers"]
