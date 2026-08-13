.PHONY: install lint test test-cov deploy mock clean validate-template

install:
	pip install -r requirements-dev.txt
	pip install -r backend/requirements.txt

lint:
	ruff check backend/
	ruff format --check backend/

test:
	pytest tests/ -v

test-cov:
	pytest tests/ --cov=backend --cov-report=term-missing

deploy:
	./deploy.sh

mock:
	python mock/server.py

clean:
	rm -rf .aws-sam __pycache__ .pytest_cache

validate-template:
	aws cloudformation validate-template --template-body file://template.yaml
