"""Pipelines package (TICKET-011+).

End-to-end wiring that composes ``sabi.capture``, ``sabi.models``,
``sabi.cleanup``, ``sabi.output``, and ``sabi.input`` into user-facing
flows. TICKET-011 ships the silent-dictation PoC; TICKET-012 adds the
audio-dictation flow and TICKET-014 will unify their JSONL streams and
``UtteranceProcessed`` shapes.
"""

from sabi.pipelines.audio_dictate import (
    DEFAULT_CONFIG_PATH as AUDIO_DICTATE_DEFAULT_CONFIG_PATH,
)
from sabi.pipelines.audio_dictate import (
    AudioDictateConfig,
    AudioDictatePipeline,
    TriggerMode,
    load_audio_dictate_config,
    run_audio_dictate,
)
from sabi.pipelines.audio_dictate import (
    PasteDecision as AudioPasteDecision,
)
from sabi.pipelines.audio_dictate import (
    UtteranceProcessed as AudioUtteranceProcessed,
)
from sabi.pipelines.events import (
    PipelineName,
    PipelinePhase,
    PipelineStatusEvent,
    UiMode,
    normalize_ui_mode,
)
from sabi.pipelines.fused_dictate import (
    DEFAULT_CONFIG_PATH as FUSED_DICTATE_DEFAULT_CONFIG_PATH,
)
from sabi.pipelines.fused_dictate import (
    FusedDictateConfig,
    FusedDictatePipeline,
    load_fused_dictate_config,
    run_fused_dictate,
)
from sabi.pipelines.fused_dictate import (
    PasteDecision as FusedPasteDecision,
)
from sabi.pipelines.fused_dictate import (
    UtteranceProcessed as FusedUtteranceProcessed,
)
from sabi.pipelines.silent_dictate import (
    DEFAULT_CONFIG_PATH as SILENT_DICTATE_DEFAULT_CONFIG_PATH,
)
from sabi.pipelines.silent_dictate import (
    PasteDecision as SilentPasteDecision,
)
from sabi.pipelines.silent_dictate import (
    SilentDictateConfig,
    SilentDictatePipeline,
    load_silent_dictate_config,
    run_silent_dictate,
)
from sabi.pipelines.silent_dictate import (
    UtteranceProcessed as SilentUtteranceProcessed,
)

DEFAULT_CONFIG_PATH = SILENT_DICTATE_DEFAULT_CONFIG_PATH
PasteDecision = SilentPasteDecision
UtteranceProcessed = SilentUtteranceProcessed

__all__ = [
    "DEFAULT_CONFIG_PATH",
    "SILENT_DICTATE_DEFAULT_CONFIG_PATH",
    "AUDIO_DICTATE_DEFAULT_CONFIG_PATH",
    "FUSED_DICTATE_DEFAULT_CONFIG_PATH",
    "PasteDecision",
    "SilentPasteDecision",
    "AudioPasteDecision",
    "FusedPasteDecision",
    "SilentDictateConfig",
    "SilentDictatePipeline",
    "AudioDictateConfig",
    "AudioDictatePipeline",
    "FusedDictateConfig",
    "FusedDictatePipeline",
    "TriggerMode",
    "UtteranceProcessed",
    "SilentUtteranceProcessed",
    "AudioUtteranceProcessed",
    "FusedUtteranceProcessed",
    "PipelineName",
    "PipelinePhase",
    "PipelineStatusEvent",
    "UiMode",
    "load_silent_dictate_config",
    "load_audio_dictate_config",
    "load_fused_dictate_config",
    "normalize_ui_mode",
    "run_silent_dictate",
    "run_audio_dictate",
    "run_fused_dictate",
]
