# Terraform is included so POLICYGATE_INCLUDE_TERRAFORM_PLAN=true behaves the
# same way inside the demo container as it does on the host.
FROM hashicorp/terraform:1.14.9 AS terraform
FROM python:3.11-slim

WORKDIR /app
COPY --from=terraform /bin/terraform /usr/local/bin/terraform
COPY requirements.lock .
RUN pip install --no-cache-dir -r requirements.lock
COPY . .

EXPOSE 8501
CMD ["streamlit", "run", "policygate/streamlit_app.py", "--server.address=0.0.0.0", "--server.port=8501"]
