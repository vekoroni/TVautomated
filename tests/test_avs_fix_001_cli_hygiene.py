"""AVS-FIX-001 W0.6 (QT-D12, QT-D13) — CLI hygiene on the dynamic path.

Two defects the quant tester found in the dispatch entry point:

* `--data-mode` is silently discarded on the dynamic path (the plan pins the
  evidence cutoff and the evening callback hard-codes AUTO), so an operator who
  typed one had no way to know it was ignored.
* `FINALISE` and `BUILD_THESIS` were bound to the same callback object, so
  nothing at the dispatch boundary enforced FINALISE's two preconditions.
"""

from __future__ import annotations

import types
import unittest

import intelligent_orchestrator as orchestrator


class FinalisePreconditionTests(unittest.TestCase):
    @staticmethod
    def _plan(run_id: str):
        return types.SimpleNamespace(pipeline_run_id=run_id)

    @staticmethod
    def _thesis(run_id: str):
        return types.SimpleNamespace(pipeline_run_id=run_id)

    def test_finalise_requires_provider_finalised_evidence(self) -> None:
        with self.assertRaises(RuntimeError) as ctx:
            orchestrator.assert_finalise_preconditions(
                self._plan("20260907_170000"),
                accepted_thesis=self._thesis("20260904_004338"),
                provider_session_finalised=False,
            )
        self.assertIn("provider-finalised", str(ctx.exception))

    def test_finalise_cannot_overwrite_the_accepted_thesis_run(self) -> None:
        """The real hole: `--finalise --run-id <accepted run>`.

        `resolve_dispatch_plan` mints a fresh run id for FINALISE only when the
        operator supplied none; an explicit --run-id is honoured, and the
        evening workflow would then write into the accepted thesis's own run
        directory.
        """
        accepted = "20260904_004338"
        with self.assertRaises(RuntimeError) as ctx:
            orchestrator.assert_finalise_preconditions(
                self._plan(accepted),
                accepted_thesis=self._thesis(accepted),
                provider_session_finalised=True,
            )
        message = str(ctx.exception)
        self.assertIn("new run identity", message)
        self.assertIn(accepted, message)

    def test_finalise_with_a_new_run_identity_is_permitted(self) -> None:
        orchestrator.assert_finalise_preconditions(
            self._plan("20260907_170000"),
            accepted_thesis=self._thesis("20260904_004338"),
            provider_session_finalised=True,
        )

    def test_finalise_without_an_accepted_thesis_is_permitted(self) -> None:
        orchestrator.assert_finalise_preconditions(
            self._plan("20260907_170000"),
            accepted_thesis=None,
            provider_session_finalised=True,
        )

    def test_guard_can_only_refuse_never_promote(self) -> None:
        """It returns None on success — it hands out no authority of any kind."""
        result = orchestrator.assert_finalise_preconditions(
            self._plan("20260907_170000"),
            accepted_thesis=None,
            provider_session_finalised=True,
        )
        self.assertIsNone(result)


class DispatchCallbackSeparationTests(unittest.TestCase):
    def test_build_thesis_and_finalise_are_distinct_callbacks(self) -> None:
        """Asserted structurally: the callback map is built inside `main()`.

        Executing `main()` would dispatch the pipeline, which AVS-IMP-FIX-001
        binding rule 1 forbids here.
        """
        import ast
        import inspect

        tree = ast.parse(inspect.getsource(orchestrator.main))
        mapping = None
        for node in ast.walk(tree):
            if not isinstance(node, ast.Dict):
                continue
            keys = [k.value for k in node.keys if isinstance(k, ast.Constant)]
            if "BUILD_THESIS" in keys and "FINALISE" in keys:
                mapping = dict(zip(keys, node.values))
                break
        self.assertIsNotNone(mapping, "dispatch callback map not found")
        build = mapping["BUILD_THESIS"]
        finalise = mapping["FINALISE"]
        self.assertIsInstance(build, ast.Name)
        self.assertIsInstance(finalise, ast.Name)
        self.assertNotEqual(
            build.id, finalise.id,
            "FINALISE and BUILD_THESIS must not share one callback object",
        )

    def test_dynamic_path_warns_that_data_mode_is_ignored(self) -> None:
        import inspect

        source = inspect.getsource(orchestrator.main)
        self.assertIn("is ignored on the dynamic dispatch path", source)


if __name__ == "__main__":
    unittest.main()
