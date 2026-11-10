$ErrorActionPreference = "Stop"

function Invoke-Target {
    param([string]$Name)

    switch ($Name) {
        "help" {
            Write-Host "Targets: init, migrate, test-unit, test-property, test-integration, lint, clean, reproduce"
        }
        "reproduce" {
            python scripts/reproduce.py
        }
        "init" {
            python -m venv .venv
            .venv\Scripts\Activate.ps1
            .venv\Scripts\pip install -e ".[dev]"
        }
        "migrate" {
            python scripts/migrations/runner.py
        }
        "test-unit" {
            python -m pytest tests/unit -q
        }
        "test-property" {
            python -m pytest tests/property -q
        }
        "test-integration" {
            python -m pytest tests/integration -q
        }
        "lint" {
            python -m ruff check .
        }
        "clean" {
            Remove-Item -Recurse -Force .pytest_cache -ErrorAction SilentlyContinue
            Remove-Item -Recurse -Force .ruff_cache -ErrorAction SilentlyContinue
            Remove-Item -Recurse -Force .mypy_cache -ErrorAction SilentlyContinue
        }
        default {
            Write-Host "Unknown target: $Name"
            exit 1
        }
}

Invoke-Target -Name $args[0]
