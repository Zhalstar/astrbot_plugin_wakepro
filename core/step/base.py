from abc import ABC, abstractmethod

from ..config import PluginConfig
from ..model import StepName, StepResult, WakeContext


class BaseStep(ABC):
    """
    所有步骤的基类。
    子类必须实现 handle()
    """

    #: 步骤名（必须覆盖）
    name: StepName

    def __init__(self, config: PluginConfig):
        self.config = config

    @abstractmethod
    async def handle(self, ctx: WakeContext) -> StepResult:
        """Process one message and return a pipeline decision.

        Args:
            ctx: Shared message context and conversation state.

        Returns:
            A result whose wake flag wakes, blocks, or leaves the message
            unchanged. The abort flag ends the pipeline. A prolong wake consumes
            one extension allowance; wake_type identifies the wake source used
            to determine whether it may start or reset the extension window.
        """
        ...  # 子类必须覆盖此处

    async def initialize(self) -> None: ...
    async def terminate(self) -> None: ...
