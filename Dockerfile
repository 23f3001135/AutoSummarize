# Use a minimal Debian base
FROM debian:bookworm-slim

# Set working directory
WORKDIR /app

# Install dependencies for building Python and system tools
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
      build-essential \
      wget \
      curl \
      ffmpeg \
      libffi-dev \
      libssl-dev \
      zlib1g-dev \
      libbz2-dev \
      libreadline-dev \
      libsqlite3-dev \
      libncursesw5-dev \
      xz-utils \
      tk-dev \
      libxml2-dev \
      libxmlsec1-dev \
      liblzma-dev \
      ca-certificates \
 && rm -rf /var/lib/apt/lists/*

# Download and compile Python 3.13.5 free-threaded
RUN wget https://www.python.org/ftp/python/3.13.5/Python-3.13.5.tgz \
 && tar -xzf Python-3.13.5.tgz \
 && cd Python-3.13.5 \
 && ./configure --disable-gil --enable-optimizations --with-lto --enable-shared \
 && make -j"$(nproc)" \
 && make altinstall \
 && cd .. \
 && rm -rf Python-3.13.5* 

# Fix shared library search path so libpython3.13t.so.1.0 can be found
RUN echo "/usr/local/lib" >> /etc/ld.so.conf.d/python3.13.conf \
 && ldconfig

# Copy requirements and install them
COPY requirements.txt .
RUN pip3.13 install --no-cache-dir -r requirements.txt gunicorn

# Non-root user setup
RUN addgroup --system app && adduser --system --ingroup app app

# Create upload directory
RUN mkdir -p /app/temporary_uploads \
 && chown -R app:app /app/temporary_uploads

# Copy app source code
COPY --chown=app:app . .

# Switch to non-root user
USER app

# Expose port
EXPOSE 8080


# Start the app with Gunicorn (single worker for stability)
ENV PYTHON_GIL=0
CMD ["gunicorn", "--bind", "0.0.0.0:8080", "app:app"]