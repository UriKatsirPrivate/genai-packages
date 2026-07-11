# genai-packages

## Articles

Every article (any `.md` file under an `articles/` directory) MUST end with this disclaimer, after a `---` horizontal rule, in italics:

> *Disclaimer: This code is provided "as-is" as a demonstration only to illustrate a potential solution. The code does not constitute a Google product or service of any kind, and Google offers no support, warranties, or liability of any kind with its regard. Whoever chooses to use this code accepts all responsibility related to it, including for its implementation, use, and ongoing maintenance. For the avoidance of doubt, this code is not eligible for the Google Open Source Software Vulnerability Rewards Program.*

When creating a new article, append it as the final section. When editing an existing article, verify it is present and add it if missing.

### No AI slop

Every article MUST go through a slop-removal pass before it is considered done: when creating a new article, and when making substantial edits to an existing one. If the `stop-slop` skill is available, apply it; otherwise enforce these rules directly:

- No em dashes. Use commas, colons, parentheses, or sentence breaks. (Exception: verbatim quoted titles and box-drawing characters in diagrams.)
- No emoji in headings.
- Kill filler adverbs: "actually", "really", "just", "simply", "genuinely", "honestly", "deliberately", "silently", "absolutely", "precisely", and similar.
- No binary-contrast formulas ("It's not X. It's Y.", "not just X but Y", negative listing before the reveal). State the point directly. Factual technical contrasts (e.g. `ttl="600s"`, not `ttl_seconds`) are fine.
- Active voice: name the actor ("The schema forces the model to..." not "The model is forced to...").
- No throat-clearing ("Here's the thing:", "Let me be clear") and no rhetorical closers ("Ready to optimize?").
- No lazy extremes ("every team", "always", "never") unless factually true of the code.
