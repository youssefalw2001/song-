from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class AceStepIntegrationPlan:
    """Configuration notes for connecting a real local ACE-Step-style model later."""

    model_name: str = "ACE-Step compatible local music model"
    expected_input: str = "prompt text, optional lyrics text, duration, seed"
    expected_output: str = "generated song file in an output directory"
    implementation_status: str = "planned"


ACE_STEP_PLAN = AceStepIntegrationPlan()
