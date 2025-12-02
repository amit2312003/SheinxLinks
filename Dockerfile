# Use Python 3.9 Slim (Debian-based) - NOT Alpine
FROM python:3.9-slim

# 1. Install Basic Tools (curl, wget, gnupg)
RUN apt-get update && apt-get install -y \
    wget \
    gnupg \
    unzip \
    curl \
    && rm -rf /var/lib/apt/lists/*

# 2. Install Google Chrome (New "Signed-By" Method)
# We use this method because 'apt-key' is deprecated and causes errors
RUN wget -q -O - https://dl-ssl.google.com/linux/linux_signing_key.pub | gpg --dearmor -o /usr/share/keyrings/google-chrome.gpg \
    && echo "deb [arch=amd64 signed-by=/usr/share/keyrings/google-chrome.gpg] http://dl.google.com/linux/chrome/deb/ stable main" > /etc/apt/sources.list.d/google-chrome.list \
    && apt-get update \
    && apt-get install -y google-chrome-stable \
    && rm -rf /var/lib/apt/lists/*

# 3. Set Working Directory
WORKDIR /app

# 4. Copy and Install Python Requirements
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 5. Copy Bot Code
COPY main.py .

# 6. Run the Bot
CMD ["python", "main.py"]
