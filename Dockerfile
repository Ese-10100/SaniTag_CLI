# 1. Use a lightweight Python base image
FROM python:3.11-slim

# 2. Set environment variables for cleaner runtime
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# 3. Create a non-root user for security
RUN useradd -m appuser

# 4. Set working directory and switch to non-root user
WORKDIR /app

# 5. Copy requirements first for caching
COPY requirements.txt /app/
RUN pip install --no-cache-dir -r requirements.txt

# 6. Copy the rest of the project files
COPY . /app/

# 7. Define the app's entrypoint
ENTRYPOINT [ "python", "sanitation.py" ]