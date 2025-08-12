.PHONY: help install install-dev format lint test test-cov check build run-container build-and-push deploy-stage clean-stage

# Default target
help: ## Show this help message
	@echo "Lightspeed to Dataverse Exporter - Development Commands"
	@echo "======================================================"
	@awk 'BEGIN {FS = ":.*##"} /^[a-zA-Z_-]+:.*##/ { printf "  \033[36m%-20s\033[0m %s\n", $$1, $$2 }' $(MAKEFILE_LIST)

# Development Environment
install: ## Install project dependencies
	uv sync

install-dev: install ## Set up development environment
	uv sync --group dev

# Code Quality
format: ## Format code with black
	uv run black .
	uv run ruff check . --fix

lint: ## Run linting with ruff
	uv run ruff check src/ tests/

test: ## Run all tests
	uv run pytest

test-cov: ## Run tests with coverage report
	uv run pytest --cov=src --cov-report=term-missing --cov-report=html

check: format lint test ## Run all code quality checks

build: ## Build the project
	podman build -t lightspeed-exporter .

build-and-push: ## Build and push container to registry
	./examples/build-and-push.sh

# OpenShift Deployment - Stage Environment
deploy-stage: build-and-push ## Deploy to stage environment
	oc apply -f examples/kubernetes/namespace.yaml
	oc apply -f examples/kubernetes/rbac.yaml
	oc apply -f examples/kubernetes/configmap-stage.yaml
	oc apply -f examples/kubernetes/job-stage.yaml

clean-stage: ## Remove stage deployment
	oc delete -f examples/kubernetes/ || true
