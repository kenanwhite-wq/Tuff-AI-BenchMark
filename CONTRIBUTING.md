# Contributing to Tuff AI Benchmark

Thank you for your interest in contributing. Contributions are welcome and appreciated.

## Contributor License Agreement

By submitting a pull request, opening an issue, or otherwise contributing code,
documentation, or other materials to this repository, you agree to the following terms:

---

**1. Grant of License**

You hereby grant Kenan White (the "Author") a perpetual, worldwide, non-exclusive,
royalty-free, irrevocable license to use, reproduce, modify, distribute, sublicense,
and otherwise exploit your contribution (the "Contribution") as part of this project
or any derivative work, in any form and by any means, with or without attribution.

**2. You Own Your Contribution**

You represent that:

- The Contribution is your original work and you have the right to grant the above license.
- The Contribution does not violate any third-party intellectual property rights,
  confidentiality obligations, or applicable laws.
- If your contribution is made in the course of your employment, you have obtained
  the necessary permissions from your employer.

**3. No Obligation**

The Author is under no obligation to accept, review, or merge any Contribution.
The Author may accept, modify, or reject Contributions at their sole discretion.

**4. No Compensation**

You understand that your Contribution is made voluntarily and without expectation
of payment, equity, or any other compensation.

**5. Project License**

Your Contribution will be subject to the same terms as the rest of the project.
The project is currently published source-visible — all rights reserved except
as explicitly granted. See the repository for the current licensing terms.

**6. Agreement**

By submitting a Contribution you confirm that you have read, understood, and
agree to these terms. You do not need to sign anything — submitting a pull
request or commit constitutes your agreement.

---

## How to Contribute

**What we need most:**

- **New benchmark parsers** — add coverage for GAIA, OSWorld, WebArena, Tau2-bench,
  or any other credible benchmark source. See `config.py` for the existing parser pattern.
- **Bug fixes** — model name normalization edge cases, feed classification errors,
  or anything else you find broken.
- **Mobile UI improvements** — the mobile layout works but could be more polished.
- **News source additions** — new RSS feeds or scrapers for the news scanner in `news_scanner.py`.

**How to add a benchmark source:**

1. Add a parser function in `config.py` that returns a DataFrame with `model` and `score` columns
2. Add the source to the `SOURCES` list with `name`, `url`, `description`, `category`, and `parser_name`
3. Add the parser to `PARSER_MAP`
4. Open a pull request with a brief description of the source and why it's worth adding

**How to submit a pull request:**

1. Fork the repository
2. Create a branch (`git checkout -b feature/your-feature-name`)
3. Make your changes
4. Test locally by running `python3 hourlyfetcher.py` and checking the output
5. Open a pull request with a clear description of what you changed and why

**Reporting bugs:**

Open a GitHub issue with:
- What you expected to happen
- What actually happened
- Steps to reproduce
- Which source or model is affected if applicable

---

*Questions? Open an issue or reach out via GitHub.*
