FROM python:3.12-alpine
WORKDIR /app
COPY runtime /app/runtime
ENV PYTHONPATH=/app
USER nobody
EXPOSE 8080 9090
ENTRYPOINT ["python", "-m", "runtime.lab.enterprise_range.server"]
