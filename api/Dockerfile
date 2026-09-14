FROM python:3.12-slim

WORKDIR /app

# Only the root requirements.txt is needed here -- api/main.py imports shared/,
# not dashboard/, so the dashboard's Streamlit/Plotly deps never end up in this image.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY shared/ shared/
COPY api/ api/

EXPOSE 8000
CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
