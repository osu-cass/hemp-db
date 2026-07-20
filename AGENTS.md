## Important rules/notes

- Do not run Python tests unless explicitly instructed to by the user, or you are actively editing the tests
- Comments should be short and to the point

## Maintainability

Long term maintainability is a core priority. If you add new functionality, first check if there is shared logic that can be extracted to a separate module. Duplicate logic across multiple files is a code smell and should be avoided. Don't be afraid to change existing code. Don't take shortcuts by just adding local logic to solve a problem.

## Project Information

This project uses Django. Use code as source of truth as docs/ may be inconsistent.

## Documentation Conventions

Use concise summary documentation for all new or changed functions and methods.

For Python code, follow PEP 257: https://peps.python.org/pep-0257/. By default, prefer short summary docstrings. Add `Args` and `Returns` sections only when they improve clarity. In typed Python code, avoid repeating type information that is already obvious from annotations unless the extra detail is genuinely useful.
