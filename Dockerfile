FROM python:3.10-slim

# Set the working directory
WORKDIR /app

# Install dependencies first (for better caching)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the source code and static assets
COPY src/ ./src/
COPY ShamQR.jpeg .

# Command to run the bot
CMD ["python", "src/main.py"]
