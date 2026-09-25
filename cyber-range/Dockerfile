FROM python:3.12-alpine
WORKDIR /app
COPY runtime /app/runtime
ENV PYTHONPATH=/app
USER nobody
EXPOSE 8080
ENTRYPOINT ["python", "-m", "runtime.server"]
