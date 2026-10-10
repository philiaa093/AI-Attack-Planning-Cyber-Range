FROM python:3.12-alpine
WORKDIR /app
COPY gateway.py /app/gateway.py
USER nobody
EXPOSE 8080
ENTRYPOINT ["python", "/app/gateway.py"]
