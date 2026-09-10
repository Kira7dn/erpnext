ARG ERPNEXT_IMAGE=frappe/erpnext:v16.31.1
FROM ${ERPNEXT_IMAGE}

# letron_api owns a YAML configuration bundle.  Install the parser into the
# immutable runtime image; containers never download dependencies at startup.
RUN /home/frappe/frappe-bench/env/bin/pip install --no-cache-dir \
    PyYAML==6.0.3 \
    'boto3>=1.34.0'
