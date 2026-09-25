FROM python:3.12-alpine
WORKDIR /app
COPY app.py /app/app.py
RUN mkdir -p /app/data \
    && echo "public file content" > /app/data/readme.txt \
    && echo "secret data" > /etc/shadow-lab-sample
USER nobody
EXPOSE 8080
ENV TARGET_ID=lab-webapp-a PORT=8080
ENTRYPOINT ["python", "/app/app.py"]
