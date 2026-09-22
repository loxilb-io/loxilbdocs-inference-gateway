<!-- Thanks for contributing to the LoxiLB Inference Gateway docs! -->

## What does this change?

Briefly describe the documentation change and its motivation.

Fixes # (issue)

## Type of change

- [ ] Fix (typo, broken link, inaccurate field/default/example)
- [ ] Improvement (clarity, expanded content)
- [ ] New page / section
- [ ] Build, CI, or tooling

## Checklist

- [ ] Documented fields, defaults, enums, and endpoints match the code repository
      (`api/swagger.yml` / `api/swagger-extras.yml`); runnable examples trace to a `cicd/` scenario.
- [ ] Partial or roadmap capabilities are marked with a status admonition (not stated as fully working).
- [ ] `mkdocs build --strict` passes locally.
- [ ] Internal links resolve; no absolute developer paths, secrets, private hosts, or internal registries.
- [ ] No internal planning/design docs or AI-assistant artifacts are included.
- [ ] Every new file has a public audience or public CI/build purpose; internal-only files remain
      under the ignored `docs/internal/` directory and were not force-added.
- [ ] Public text contains no internal work-package, test-case, branch, approval, or tracking IDs.
- [ ] Commits follow [Conventional Commits](https://www.conventionalcommits.org/).
- [ ] Commits are signed off (DCO): `git commit -s`.
