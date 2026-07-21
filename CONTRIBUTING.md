# Contributing to Our Project

First off, thank you for considering contributing! It's people like you that make this project great. We welcome any type of contribution, not just code.

This document is a guide to help you through the process of contributing.

## How Can I Contribute?

There are many ways to contribute, from improving the documentation, submitting bug reports and feature requests, or writing code which can be incorporated into the project itself.

### Reporting Bugs

If you find a bug, please first check our Azure DevOps board or GitHub issues to see if it has already been reported. If not, please file a new work item (or open a GitHub issue using the bug report template).

### Suggesting Enhancements

If you have an idea for a new feature or an improvement to an existing one, please open a work item on our Azure DevOps board to discuss it. This allows us to coordinate our efforts and prevent duplication of work.

Provide a clear description of the enhancement and why you think it would be valuable.

### Submitting Pull Requests

If you'd like to contribute code, that's fantastic! First, ensure that a work item exists for the enhancement you want to implement. If not, please create one. If it's a small change, you can also submit a pull request directly without creating a work item, but be aware that your pull request may not be accepted if it's not aligned to our project's direction. Creating a work item first is recommended to ensure that your contribution aligns with our project's direction.

From there, follow these steps:

1.  **Clone the repository** to your local machine and create a feature branch off `main`.
2.  **Set up your development environment**. Follow the `Local Setup` guide in [`docs/DEVELOP.md`](docs/DEVELOP.md).
3.  **Add or update tests**.  Run the test suite to make sure everything is still working. Add or update tests as needed.
```bash
python manage.py test
```
4.  **Update documentation**. If you've added a new feature or changed an existing one, please update the relevant documentation (e.g., `README.md`).
5.  **Commit your changes**. Please write a clear, concise commit message. We follow the [Conventional Commits](https://www.conventionalcommits.org/en/v1.0.0/) specification.
6.  **Open a Pull Request** to the `main` branch of the original repository. Provide a clear description of the changes you've made.

## Pull Request Guidelines

*   The PR title should be descriptive.
*   The PR description should explain the "what" and "why" of the changes.
*   Ensure all automated checks are passing.
*   Please link the related Azure DevOps work item in the description.
*   Be prepared to address feedback from the maintainers.

Thank you again for your interest in contributing!
