# Security Policy

## Supported Versions

Security fixes are backported to the latest release. Older versions should be
upgraded promptly.

| Version | Supported          |
|---------|--------------------|
| latest  | ✅                |
| older   | ❌ (please upgrade)|

## Reporting a Vulnerability

If you find a security issue in `text-cleaning-engine`, **do not open a public
issue**. Report it privately:

1. Use **GitHub Security Advisories**:
   https://github.com/SpiralQWQ/text-cleaning-engine/security/advisories/new
2. If you cannot use the form, open an issue titled `[SECURITY] …` and flag it
   `confidential` (issues are not private by default, so prefer the advisory
   form whenever possible).

Please include:

- The affected version(s).
- A minimal reproducer (input that triggers the issue).
- Your assessment of impact (e.g. data loss, information disclosure).

The maintainer will acknowledge the report, and — once a fix lands — you'll be
credited in the changelog (unless you prefer to stay anonymous).

## Scope

This project cleans text; it does not run untrusted code by default. The main
risk surfaces are:

- **Malformed input / fuzz** — handled by defensive guards (`clean_text`,
  `clean_asr_json`, `normalize_sentences` are hardened against non-str / `None`
  inputs). Extend the guards if you find a crash.
- **Configuration exfiltration** — `.env` / environment variables hold optional
  tool paths; they are read but never written or logged in cleartext by the
  engine.
- **Rule injection** — `cleaning_rules.yaml` values are treated as data, not
  executed code.

If you find a crash on unexpected input, that is a valid security report.
