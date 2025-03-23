FROM python:3.9-slim

WORKDIR /app

# copy requirements files
COPY requirements.txt .

#install dependencies 
RUN pip install --no-cache-dir -r requirements.txt

# Copy project
COPY . .

# verify that uvicorn is installed
RUN pip list | grep uvicorn

# Command to run the application
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
