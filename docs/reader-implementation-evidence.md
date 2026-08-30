# PrepPilot private reader implementation evidence

Run nonce: `9bd182f0-d5c6-4579-b8e7-91de02ee52b0`

Mission pointer: `PROMPTS.txt` SHA-256 `93050b69b07b9ca542fc06baf816b5aa7e9d21ee4d3db660b991ff83f6bed518`, 1006 bytes.

Roadmap pointer: `ROADMAP.md` SHA-256 `0b929c314a0bbd07317446d2aad0b800b6dccb7a65661dfa1c9b8f7423714150`, 25661 bytes.

## Implementation inventory

- Backend: `app/book_service.py`, `app/config.py`, `app/db.py`, `app/main.py`, `app/models.py`, and `app/routers/book_routes.py`.
- Backend tests: `tests/test_book_learning.py`, `tests/test_reader_companion.py`, `tests/test_dev_isolation.py`, `tests/test_deploy_dev_contract.py`, and `tests/test_backend_coverage_gate.py`.
- Frontend: `src/App.tsx`, `src/api.ts`, `src/pages/MakeMeLearn.tsx`, `src/pages/TopicDetail.tsx`, `src/styles.css`, `src/test/setup.ts`, and `vite.config.ts`.
- Frontend tests: `src/App.test.tsx`, `src/api.test.ts`, `src/pages/MakeMeLearn.test.tsx`, `src/pages/TopicDetail.test.tsx`, and `tests/reader-runtime-contract.test.ts`.
- Safety/gates: `deploy/deploy-dev.sh`, `deploy/check-dev-storage.py`, and `scripts/check_backend_module_coverage.py`.
- Evidence: this file.

The pre-existing base-reader diff was treated as candidate implementation and retained where correct. It was extended or corrected for owner-contained canonical paths, cache and deletion behavior, typed page-grounded chat/citations, reader state, literal search, integrated UI, and dev-only deployment attestation.

## Red then green evidence

- RDR-07 initial red: `ENVIRONMENT=production DATABASE_URL='sqlite:///:memory:' BOOK_STORAGE_DIR='/tmp/preppilot-wave-c-red-books' uv run python -m unittest tests.test_deploy_dev_contract tests.test_backend_coverage_gate -q` ran 6 tests with 6 intended failures for the absent untracked-payload guard, pre-sync dev isolation attestation, post-health attestation, and backend coverage checker.
- RDR-07 targeted green: the same deploy/coverage contract tests plus `tests.test_dev_isolation` ran 8/8 successfully after the minimal safety implementation.
- Final backend: `ENVIRONMENT=production DATABASE_URL='sqlite:///:memory:' BOOK_STORAGE_DIR='/tmp/preppilot-reader-coverage-books' uv run --group dev coverage run --branch -m unittest discover -s tests -q` passed 213/213 in 8.740 seconds.
- Final frontend: `npm test` passed 87/87 across 10 files without a Node local-storage workaround. The changed-coverage checker self-tests passed 6/6.
- Build: `npm run build` completed successfully; TypeScript and Vite transformed 2,319 modules.

## Coverage gates

Backend changed executable lines are 99%: 331 lines, one uncovered line. Every touched backend module meets the 95% line and branch floors:

| Module | Lines | Branches |
| --- | ---: | ---: |
| `app/book_service.py` | 99.32% | 96.51% |
| `app/config.py` | 100.00% | 100.00% |
| `app/db.py` | 100.00% | 100.00% |
| `app/main.py` | 100.00% | 100.00% |
| `app/models.py` | 100.00% | 100.00% |
| `app/routers/book_routes.py` | 96.89% | 96.00% |

Every touched frontend module meets the 95% changed-line, line, statement, function, and branch floors:

| Module | Changed lines | Lines | Statements | Functions | Branches |
| --- | ---: | ---: | ---: | ---: | ---: |
| `src/App.tsx` | 100.00% | 100.00% | 100.00% | 100.00% | 100.00% |
| `src/api.ts` | 100.00% | 100.00% | 100.00% | 100.00% | 99.20% |
| `src/pages/MakeMeLearn.tsx` | 97.35% | 97.49% | 98.32% | 97.33% | 95.63% |
| `src/pages/TopicDetail.tsx` | 100.00% | 100.00% | 100.00% | 100.00% | 95.77% |

## Safety and rollback status

- `bash -n deploy/deploy-dev.sh` and `git diff --check` pass.
- The dev deploy contract blocks untracked backend/frontend payload, attests explicit development database and book-storage isolation before sync/reload, preserves the dev `.env`, and requires the same isolation booleans from health afterward.
- No deployment, commit, push, or staging was performed. The index is empty. The pre-existing `.claude/settings.json` remains untracked and untouched.
- Production configuration/data and Inference course implementation/data remain in place for rollback. Only visible UI entry points are removed or redirected to Read a book.
- Independent G5 re-review passed the exact 50-result truncation contract, typed chat/citation response schemas, evidence, correctness, and security checks.
- Independent G6 same-origin browser verification passed at 1440x900: after 750px page scroll, the fixed dev banner ended at 34px and the chat panel remained at 34px with internal chat scrolling. Resume, bookmarks, literal search, live page-grounded chat/citation jumps, mobile stacking, owner isolation, and private no-store responses also passed.
- Remote dev deployment was deliberately not claimed at the implementation frontier and remains the final release action.

Implementation verdict: RDR-00 through RDR-07, G4, G5, and G6 are complete. Release readiness is pending only the authorized isolated dev deployment and post-deploy attestation.
