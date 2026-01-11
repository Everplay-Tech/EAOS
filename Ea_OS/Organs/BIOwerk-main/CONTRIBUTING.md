# Contributing to BIOwerk

Thank you for your interest in contributing to BIOwerk! This document provides guidelines and instructions for setting up your development environment and contributing to the project.

## Table of Contents

- [Development Setup](#development-setup)
- [Code Quality Standards](#code-quality-standards)
- [Development Workflow](#development-workflow)
- [Testing](#testing)
- [Commit Guidelines](#commit-guidelines)
- [Pull Request Process](#pull-request-process)

## Development Setup

### Prerequisites

- Python 3.10 or higher
- Docker and Docker Compose
- Git
- Make (optional, but recommended)

### Initial Setup

1. **Clone the repository:**
   ```bash
   git clone <repository-url>
   cd BIOwerk
   ```

2. **Set up Python virtual environment:**
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate  # On Windows: .venv\Scripts\activate
   ```

3. **Install development dependencies:**
   ```bash
   make install-dev
   # Or manually:
   pip install -r requirements-dev.txt
   pre-commit install
   ```

4. **Configure environment variables:**
   ```bash
   cp .env.example .env
   # Edit .env with your configuration
   ```

5. **Start Docker services:**
   ```bash
   make docker-up
   ```

## Code Quality Standards

This project maintains high code quality standards using multiple tools:

### Formatting

- **Black**: Automatic code formatting (line length: 120)
- **isort**: Import sorting and organization

Run formatters:
```bash
make format
```

### Linting

- **Flake8**: Style guide enforcement
- **Pylint**: Code analysis and quality checking

Run linters:
```bash
make lint
```

### Type Checking

- **MyPy**: Static type checking

Run type checker:
```bash
make type-check
```

### Security

- **Bandit**: Security vulnerability detection
- **Safety**: Dependency vulnerability scanning
- **detect-secrets**: Secret detection

Run security checks:
```bash
make security
```

## Development Workflow

### Pre-commit Hooks

Pre-commit hooks are automatically installed and run before each commit. They include:

- Code formatting (Black, isort)
- Linting (Flake8, Pylint)
- Type checking (MyPy)
- Security scanning (Bandit, detect-secrets)
- YAML/JSON validation
- Trailing whitespace removal
- Large file detection

To run pre-commit hooks manually:
```bash
make pre-commit
# Or:
pre-commit run --all-files
```

### Common Development Tasks

#### Run All Checks
```bash
make check-all
```

This runs:
1. Code formatting
2. Linting
3. Type checking
4. Security scanning
5. Tests with coverage

#### Run Tests
```bash
# All tests
make test

# With coverage
make test-cov

# Unit tests only
make test-unit

# Integration tests
make test-integration

# E2E tests
make test-e2e

# Fast parallel tests
make test-fast
```

#### Run Services
```bash
# Start mesh service
make run-mesh

# Start specific service
make run-service SERVICE=synapse
```

#### Database Migrations
```bash
# Create new migration
make migrations-create MSG="add users table"

# Apply migrations
make migrations-upgrade

# Rollback migration
make migrations-downgrade

# View migration history
make migrations-history
```

## Testing

### Test Organization

- `tests/` - Unit tests
- `tests/e2e/` - End-to-end tests
- `tests/conftest.py` - Shared test fixtures

### Writing Tests

1. **Use pytest**: All tests should use pytest framework
2. **Async support**: Use `pytest-asyncio` for async tests
3. **Coverage**: Aim for >80% code coverage
4. **Markers**: Use appropriate test markers:
   - `@pytest.mark.slow` - Slow tests
   - `@pytest.mark.integration` - Integration tests
   - `@pytest.mark.e2e` - End-to-end tests
   - `@pytest.mark.security` - Security tests

Example test:
```python
import pytest
from matrix.auth import verify_token

@pytest.mark.asyncio
async def test_verify_token():
    """Test token verification."""
    token = "test-token"
    result = await verify_token(token)
    assert result is not None
```

### Test Configuration

Test settings are configured in `pyproject.toml`:
- Coverage reports in HTML and XML
- Strict marker enforcement
- Async mode enabled

## Commit Guidelines

### Commit Message Format

Follow the Conventional Commits specification:

```
<type>(<scope>): <subject>

<body>

<footer>
```

**Types:**
- `feat`: New feature
- `fix`: Bug fix
- `docs`: Documentation changes
- `style`: Code style changes (formatting, etc.)
- `refactor`: Code refactoring
- `test`: Test additions or changes
- `chore`: Build process or auxiliary tool changes
- `perf`: Performance improvements
- `security`: Security improvements

**Examples:**
```
feat(auth): add JWT token refresh endpoint

Implements token refresh functionality to allow users to
obtain new access tokens without re-authenticating.

Closes #123
```

```
fix(database): resolve connection pool exhaustion

Increases connection pool size and adds proper connection
cleanup to prevent pool exhaustion under high load.
```

### Pre-commit Validation

Before committing:
1. All pre-commit hooks must pass
2. All tests must pass
3. Code coverage should not decrease

## Pull Request Process

### Creating a Pull Request

1. **Create a feature branch:**
   ```bash
   git checkout -b feature/your-feature-name
   ```

2. **Make your changes:**
   - Write code following our style guidelines
   - Add tests for new functionality
   - Update documentation as needed

3. **Run quality checks:**
   ```bash
   make check-all
   ```

4. **Commit your changes:**
   ```bash
   git add .
   git commit -m "feat: add your feature"
   ```

5. **Push to your branch:**
   ```bash
   git push origin feature/your-feature-name
   ```

6. **Create Pull Request:**
   - Use a clear, descriptive title
   - Fill out the PR template completely
   - Reference related issues
   - Request review from maintainers

### PR Requirements

Before merging, your PR must:

- [ ] Pass all CI checks
- [ ] Include tests for new functionality
- [ ] Maintain or improve code coverage
- [ ] Update relevant documentation
- [ ] Follow code style guidelines
- [ ] Have no merge conflicts
- [ ] Be approved by at least one maintainer

### Review Process

1. **Automated checks**: CI pipeline runs automatically
2. **Code review**: Maintainers review code quality and design
3. **Testing**: Reviewers may test functionality manually
4. **Feedback**: Address review comments and update PR
5. **Approval**: Once approved, maintainers will merge

## Code Style Guidelines

### Python Style

- Follow PEP 8 with line length of 120 characters
- Use type hints for function signatures
- Write docstrings for public functions and classes (Google style)
- Keep functions focused and small
- Use meaningful variable names

### Example:

```python
from typing import Optional

async def get_user_by_id(user_id: int) -> Optional[dict]:
    """Retrieve a user by their ID.

    Args:
        user_id: The unique identifier of the user.

    Returns:
        User data as a dictionary, or None if not found.

    Raises:
        DatabaseError: If database connection fails.
    """
    # Implementation
    pass
```

## Additional Resources

- [Python Style Guide (PEP 8)](https://www.python.org/dev/peps/pep-0008/)
- [Conventional Commits](https://www.conventionalcommits.org/)
- [pytest Documentation](https://docs.pytest.org/)
- [FastAPI Best Practices](https://fastapi.tiangolo.com/tutorial/)

## Getting Help

If you need help:

1. Check existing documentation
2. Search for similar issues
3. Ask in project discussions
4. Contact maintainers

## License

By contributing to BIOwerk, you agree that your contributions will be licensed under the project's MIT License.
