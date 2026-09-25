FROM python:3.12-alpine
WORKDIR /app
COPY app.py /app/app.py
RUN mkdir -p /app/uploads \
    && echo "report data" > /app/uploads/report.txt \
    && echo "confidential" > /etc/private-lab-sample
USER nobody
EXPOSE 8080
ENV TARGET_ID=lab-webapp-b PORT=8080
ENTRYPOINT ["python", "/app/app.py"]
