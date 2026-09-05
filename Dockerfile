FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 MANDATE_DATA_DIR=/data PORT=8000
WORKDIR /app
COPY requirements.lock .
RUN pip install --no-cache-dir -r requirements.lock && useradd --uid 10001 --create-home mandate && mkdir /data && chown mandate:mandate /data
COPY --chown=mandate:mandate mandate ./mandate
COPY --chown=mandate:mandate static ./static
COPY --chown=mandate:mandate scripts ./scripts
USER 10001:10001
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=3s CMD python -c "import urllib.request,os; urllib.request.urlopen('http://127.0.0.1:'+os.getenv('PORT','8000')+'/healthz',timeout=2)"
CMD ["/app/scripts/entrypoint.sh"]
