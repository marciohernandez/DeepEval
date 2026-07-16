"""BotInvokerFactory — imports and validates bots.<id>.invocation.invoker_class;
no fixed registry. A new invocation type requires only a subclass and
configuration (M4.1, R6).
"""
from __future__ import annotations

import importlib
import inspect

from deepeval_platform.config.config_manager import ConfigManager
from deepeval_platform.synthetic.bot_invoker_base import BotInvokerBase


class BotInvokerConfigError(Exception):
    pass


class BotInvokerFactory:
    @classmethod
    def create(cls, bot_id: str, config: ConfigManager | None = None) -> BotInvokerBase:
        config = config if config is not None else ConfigManager.instance()

        try:
            dotted_path = config.get(f"bots.{bot_id}.invocation.invoker_class")
        except Exception as exc:
            raise BotInvokerConfigError(
                f"No invocation.invoker_class configured for bot {bot_id!r}"
            ) from exc

        module_path, _, class_name = dotted_path.rpartition(".")
        try:
            module = importlib.import_module(module_path)
            invoker_cls = getattr(module, class_name)
        except Exception as exc:
            raise BotInvokerConfigError(
                f"Cannot import invoker class {dotted_path!r} for bot {bot_id!r}"
            ) from exc

        if not (inspect.isclass(invoker_cls) and issubclass(invoker_cls, BotInvokerBase)):
            raise BotInvokerConfigError(
                f"{dotted_path!r} is not a BotInvokerBase subclass"
            )
        if inspect.isabstract(invoker_cls):
            raise BotInvokerConfigError(
                f"{dotted_path!r} is abstract and cannot be instantiated"
            )

        kwargs: dict[str, object] = {"bot_id": bot_id}
        parameters = inspect.signature(invoker_cls.__init__).parameters
        for name in parameters:
            if name in ("self", "bot_id"):
                continue
            try:
                kwargs[name] = config.get(f"bots.{bot_id}.invocation.{name}")
            except Exception as exc:
                raise BotInvokerConfigError(
                    f"Missing config bots.{bot_id}.invocation.{name} required by "
                    f"{dotted_path!r}"
                ) from exc

        return invoker_cls(**kwargs)
