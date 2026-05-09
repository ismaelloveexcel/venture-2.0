# Copilot Prompts — Code Generation & Review

---

## Build a Feature

```
Build [feature description] in [language/framework].
Requirements:
- [requirement 1]
- [requirement 2]
- [requirement 3]
Follow OWASP security best practices. No external dependencies unless necessary.
Add inline comments for non-obvious logic only.
```

---

## Security Review

```
Review this code for security vulnerabilities (focus on OWASP Top 10):
[paste code]
Flag: injection risks, auth issues, sensitive data exposure, input validation gaps.
Provide fixed version for each issue found.
```

---

## Explain & Improve

```
Explain what this code does in plain English, then suggest 3 improvements:
[paste code]
Improvements should focus on: security, performance, maintainability.
```

---

## Debug This Error

```
I'm getting this error:
ERROR: [paste error message]

In this code:
[paste relevant code]

What's causing it? Give me the fixed version and explain what was wrong.
```

---

## Write an API Endpoint

```
Write a [GET/POST/PUT/DELETE] endpoint for [purpose] in Express.js.
Input: [describe expected request body or params]
Output: [describe expected response]
Include: input validation, error handling, rate limiting note.
Security: sanitise inputs, no SQL injection risks, return generic error messages to client.
```

---

## Generate a Python Automation Script

```
Write a Python script that:
1. [task 1]
2. [task 2]
3. [task 3]

Input source: [file / API / stdin]
Output: [file / stdout / API call]
Use only standard library + [specific package if needed].
Handle errors gracefully. No hardcoded credentials — use environment variables.
```
