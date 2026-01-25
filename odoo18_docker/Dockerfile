FROM odoo:18.0

USER root

# Install additional System dependencies if needed (e.g. for PDF generation or specificlibs)
RUN apt-get update && apt-get install -y \
    build-essential \
    python3-dev \
    libldap2-dev \
    libsasl2-dev \
    && rm -rf /var/lib/apt/lists/*

# Install python packages (Example)
# COPY requirements.txt /tmp/requirements.txt
# RUN pip3 install -r /tmp/requirements.txt
RUN pip3 install --upgrade pip
RUN pip3 install pandas requests

# Create directory for custom configuration if preferred
COPY ./config /etc/odoo

# Switch back to odoo user for security
USER odoo
