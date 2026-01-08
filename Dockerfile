FROM python:3.12-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY bot.py database.py handlers.py scheduler.py ./

# Create data directory for SQLite database
RUN mkdir -p /app/data

# Run the bot
CMD ["python", "bot.py"]
