FROM python:3.12-alpine
WORKDIR /app
COPY app.py /app/app.py
RUN mkdir -p /app/data \
    && echo "public readme" > /app/data/readme.txt
USER nobody
EXPOSE 8080
ENV TARGET_ID=lab-clean-control PORT=8080
ENTRYPOINT ["python", "/app/app.py"]
