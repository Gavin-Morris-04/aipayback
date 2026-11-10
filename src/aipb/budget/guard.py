"""The budget guard: no LLM call happens without passing through here.

Model: reserve, then settle.
1. Before a run, estimate the worst case (input estimate + max_tokens output for every
   request) and reserve it. Refuse if spent + outstanding reservations + this estimate
   would pass the cap. Runs above the confirm threshold need confirm=True.
2. Each call inside the run must fit inside what is left of that run's reservation.
3. Actual cost (from the API's usage numbers) is written to the ledger; finishing the run
   releases whatever was reserved but not spent.

A run that crashes stays "open" and keeps its reservation (fail closed) until someone
checks it and releases it with `aipb release-run`.
"""

from __future__ import annotations

import subprocess
import uuid
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from types import TracebackType

import yaml

from aipb.budget.ledger import Ledger, RunEvent, utc_now
from aipb.budget.pricing import PricingTable


class BudgetError(RuntimeError):
    pass


class BudgetExceeded(BudgetError):
    pass


class ConfirmationRequired(BudgetError):
    pass


class PromptTooLarge(BudgetError):
    pass


class RunBudgetExceeded(BudgetError):
    pass


def usd(value: Decimal) -> str:
    """Format dollars for people: 4 decimals below a cent, 2 otherwise."""
    if value != 0 and abs(value) < Decimal("0.01"):
        return f"${value:.4f}"
    return f"${value:.2f}"


@dataclass(frozen=True)
class BudgetConfig:
    total_credit_usd: Decimal
    app_cap_usd: Decimal
    reserve_usd: Decimal
    reserve_unlocked_usd: Decimal
    confirm_threshold_usd: Decimal
    max_prompt_tokens: int

    def __post_init__(self) -> None:
        if self.app_cap_usd + self.reserve_usd > self.total_credit_usd:
            raise ValueError("app_cap_usd + reserve_usd is more than total_credit_usd")
        if not Decimal("0") <= self.reserve_unlocked_usd <= self.reserve_usd:
            raise ValueError("reserve_unlocked_usd must be between 0 and reserve_usd")

    @property
    def cap(self) -> Decimal:
        return self.app_cap_usd + self.reserve_unlocked_usd

    @property
    def reserve_locked_usd(self) -> Decimal:
        return self.reserve_usd - self.reserve_unlocked_usd

    @classmethod
    def load(cls, path: Path) -> BudgetConfig:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        return cls(
            total_credit_usd=Decimal(str(raw["total_credit_usd"])),
            app_cap_usd=Decimal(str(raw["app_cap_usd"])),
            reserve_usd=Decimal(str(raw["reserve_usd"])),
            reserve_unlocked_usd=Decimal(str(raw["reserve_unlocked_usd"])),
            confirm_threshold_usd=Decimal(str(raw["confirm_threshold_usd"])),
            max_prompt_tokens=int(raw["max_prompt_tokens"]),
        )


@dataclass(frozen=True)
class BudgetStatus:
    spent: Decimal
    reserved: Decimal
    cap: Decimal
    reserve_locked: Decimal
    total_credit: Decimal

    @property
    def remaining(self) -> Decimal:
        return self.cap - self.spent - self.reserved


def _git_sha(cwd: Path | None) -> str:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True,
            text=True,
            cwd=cwd,
            timeout=5,
            check=False,
        )
        return out.stdout.strip() if out.returncode == 0 else ""
    except (OSError, subprocess.SubprocessError):
        return ""


class BudgetGuard:
    def __init__(
        self,
        config: BudgetConfig,
        ledger: Ledger,
        pricing: PricingTable,
        *,
        device: str = "unknown",
        repo_dir: Path | None = None,
    ) -> None:
        self.config = config
        self.ledger = ledger
        self.pricing = pricing
        self.device = device
        self.repo_dir = repo_dir

    def status(self) -> BudgetStatus:
        return BudgetStatus(
            spent=self.ledger.total_spent(),
            reserved=self.ledger.outstanding_reservations(),
            cap=self.config.cap,
            reserve_locked=self.config.reserve_locked_usd,
            total_credit=self.config.total_credit_usd,
        )

    def check_prompt_size(self, prompt_tokens: int) -> None:
        if prompt_tokens > self.config.max_prompt_tokens:
            raise PromptTooLarge(
                f"Prompt is ~{prompt_tokens:,} tokens; the limit is "
                f"{self.config.max_prompt_tokens:,} (Haiku 5.5 charges 5x above 100k). "
                "Split the input."
            )

    def preflight(self, estimate: Decimal, *, confirm: bool) -> BudgetStatus:
        st = self.status()
        if estimate > st.remaining:
            raise BudgetExceeded(
                f"Worst-case estimate {usd(estimate)} is more than the {usd(st.remaining)} "
                f"left under the {usd(st.cap)} cap (spent {usd(st.spent)}, "
                f"reserved {usd(st.reserved)}). Refusing to run."
            )
        if estimate > self.config.confirm_threshold_usd and not confirm:
            raise ConfirmationRequired(
                f"Worst-case estimate is {usd(estimate)}, above the "
                f"{usd(self.config.confirm_threshold_usd)} threshold. Re-run with --confirm."
            )
        return st

    def start_run(self, *, command: str, stage: str, estimate: Decimal, confirm: bool) -> Run:
        self.preflight(estimate, confirm=confirm)
        run_id = f"run-{utc_now()[:10]}-{uuid.uuid4().hex[:8]}"
        self.ledger.append_run_event(
            RunEvent(
                event="start",
                run_id=run_id,
                ts=utc_now(),
                command=command,
                stage=stage,
                estimate_usd=estimate,
                reserved_usd=estimate,
                git_sha=_git_sha(self.repo_dir),
                device=self.device,
            )
        )
        return Run(guard=self, run_id=run_id, stage=stage, reserved=estimate)

    def finish_run(self, run_id: str, status: str) -> None:
        self.ledger.append_run_event(
            RunEvent(event="finish", run_id=run_id, ts=utc_now(), status=status)
        )

    def release_run(self, run_id: str) -> None:
        state = self.ledger.runs().get(run_id)
        if state is None:
            raise BudgetError(f"Unknown run {run_id}")
        if not state.is_open:
            raise BudgetError(f"Run {run_id} is already finished")
        self.finish_run(run_id, "released")


class Run:
    """One reservation. Use as a context manager so the reservation is always settled."""

    def __init__(self, *, guard: BudgetGuard, run_id: str, stage: str, reserved: Decimal):
        self.guard = guard
        self.run_id = run_id
        self.stage = stage
        self.reserved = reserved
        self.spent = Decimal("0")
        self.calls = 0
        self.finished = False

    @property
    def left(self) -> Decimal:
        return self.reserved - self.spent

    def authorize_call(self, worst_case: Decimal) -> None:
        if self.finished:
            raise BudgetError(f"Run {self.run_id} is finished")
        if worst_case > self.left:
            raise RunBudgetExceeded(
                f"Next call could cost up to {usd(worst_case)} but run {self.run_id} has "
                f"only {usd(self.left)} of its reservation left. Stopping."
            )

    def record_spend(self, cost: Decimal) -> None:
        self.spent += cost
        self.calls += 1

    def finish(self, status: str = "ok") -> None:
        if not self.finished:
            self.guard.finish_run(self.run_id, status)
            self.finished = True

    def __enter__(self) -> Run:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.finish("ok" if exc_type is None else "error")
