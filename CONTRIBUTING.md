# Contributing

Run `python -m unittest discover -s tests -v` before opening a pull request.
Keep the runtime dependency-free and Python 3.10 compatible.

For a new rule, document the existing-client behavior, add request and response
regression cases, test references where relevant, and update docs/scope.md.
Prefer a review warning over a claim of compatibility that the engine cannot
justify. Rule codes and JSON finding fields are part of the public interface.

For bugs, include minimal baseline/candidate JSON, actual findings, expected
findings, Python version and the command used. Avoid uploading private APIs or
credentials. Small focused changes are easier to review.
