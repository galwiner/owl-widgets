# Contributing to OWL

Thanks for helping improve OWL. Bug reports, teaching examples, documentation fixes, and focused pull requests are welcome.

## Before starting

- Use [GitHub Issues](https://github.com/galwiner/owl-widgets/issues) for bugs and feature proposals.
- For substantial changes, open an issue first so the design and scope can be discussed.
- Report security concerns privately as described in [`SECURITY.md`](SECURITY.md), not in a public issue.
- OWL is in a `0.x` development series, so APIs may evolve between minor releases.

## Development setup

OWL requires Python 3.12 or newer. From the repository root, run the Python tests against the checkout:

```sh
uv run --no-project --refresh-package owl-widgets --with . --with pytest pytest tests
```

Run the strict notebook checks:

```sh
uvx --from marimo==0.25.1 marimo check --strict \
  notebooks/optics_basics.py \
  notebooks/apertures.py \
  notebooks/keplerian_telescope.py
```

Run browser tests (the first Playwright run downloads Chromium):

```sh
npm exec --yes --package=@playwright/test -- playwright install chromium
npm exec --yes --package=@playwright/test -- \
  node --test tests/test_frontend.mjs tests/test_studies_frontend.mjs
```

Check the distributions when changing packaging or bundled assets:

```sh
uv build
uvx --from twine twine check dist/*
```

## Pull requests

- Keep changes focused and consistent with the existing code.
- Add or update tests for behavior changes and bug fixes.
- Keep calculations in Python rather than duplicating scientific logic in JavaScript.
- Preserve offline operation: runtime assets must be packaged locally, not loaded from a CDN.
- Preserve keyboard access, visible focus, readable contrast, reduced-motion behavior, and encodings that do not rely on color alone.
- Check hard-aperture and FFT changes for sampling sensitivity rather than treating one grid as ground truth.
- Update notebooks and documentation when a public interface changes.
- Do not commit generated distributions, virtual environments, caches, or credentials.

By contributing, you agree that your contribution may be distributed under the repository's MIT License.
