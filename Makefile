# Customer Request Agent — common commands.
# Quickstart (no API key needed — runs in deterministic mock mode):
#     make install && make samples

PY ?= python

.PHONY: install run samples package deploy destroy clean

install:
	$(PY) -m pip install -r requirements.txt

# Single request:  make run REQUEST="Refund for ORD1001, this is CUST001. $$30"
run:
	$(PY) -m agent.cli "$(REQUEST)"

# Run every bundled sample request through the agent.
samples:
	$(PY) -m agent.cli --samples

# --- AWS deploy (Terraform; sync API Gateway -> Lambda) ---
# Build the Lambda zip (agent package + dependencies).
package:
	rm -rf build lambda.zip
	mkdir -p build
	$(PY) -m pip install -r requirements.txt -t build >/dev/null
	cp -r agent build/agent
	cd build && zip -qr ../lambda.zip .

deploy: package
	cd infra && terraform init && terraform apply -auto-approve

destroy:
	cd infra && terraform destroy -auto-approve

clean:
	rm -rf build lambda.zip
