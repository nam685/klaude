.PHONY: help dev install lint format test clean

help: ## Show available commands
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-15s\033[0m %s\n", $$1, $$2}'

install: ## Install dependencies
	uv sync

dev: ## Run klaude in interactive REPL mode
	uv run klaude

lint: ## Run ruff linter
	uvx ruff check src/

format: ## Format code with ruff
	uvx ruff format src/

test: ## Run tests
	uv run pytest

clean: ## Remove build artifacts and caches
	rm -rf build/ dist/ *.egg-info .pytest_cache __pycache__
	find src -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true

backlog: ## Show open backlog tickets
	@grep -l "status: todo\|status: in-progress\|status: blocked" backlog/*.md 2>/dev/null || echo "No open tickets"

backlog-high: ## Show high-priority backlog tickets
	@grep -l "priority: critical\|priority: high" backlog/*.md 2>/dev/null || echo "No high-priority tickets"
