FROM python:3.12-alpine
WORKDIR /app
COPY app.py /app/app.py
RUN mkdir -p /app/data/invoices \
    && chown -R nobody:nobody /app/data
USER nobody
EXPOSE 8080
ENV TARGET_ID=lab-ecommerce PORT=8080
ENTRYPOINT ["python", "/app/app.py"]
