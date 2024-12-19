FROM python:3.11-slim

RUN pip install uv 

WORKDIR /app
COPY . .

RUN uv pip install --system -r requirements.txt

ENV PORT=8080
CMD ["./start.sh"]
