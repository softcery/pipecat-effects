"""One voice bot with an 8 stage chain on its output. Run it with the pipecat runner.

It needs pipecat-ai[runner,webrtc,openai,silero] and OPENAI_API_KEY.
"""

import os

from pipecat.audio.vad.silero import SileroVADAnalyzer
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.worker import PipelineWorker
from pipecat.processors.aggregators.llm_context import LLMContext
from pipecat.processors.aggregators.llm_response_universal import (
    LLMContextAggregatorPair,
    LLMUserAggregatorParams,
)
from pipecat.runner.run import main
from pipecat.runner.types import RunnerArguments
from pipecat.runner.utils import create_transport
from pipecat.services.openai.llm import OpenAILLMService
from pipecat.services.openai.stt import OpenAISTTService
from pipecat.services.openai.tts import OpenAITTSService
from pipecat.transports.base_transport import TransportParams
from pipecat.workers.runner import WorkerRunner

from pipecat_effects import (
    AGC,
    Biquad,
    Compressor,
    DeEsser,
    Effects,
    EffectsFilter,
    FilterMixer,
    Limiter,
    Saturation,
)

PROMPT = "You are a voice assistant. Answer in one short sentence."

CHAIN: Effects = (
    AGC(target_lufs=-20.0),
    Biquad(kind="highpass", hz=90.0),
    Biquad(kind="lowshelf", hz=200.0, gain_db=2.5),
    Biquad(kind="peak", hz=3200.0, q=1.2, gain_db=-2.0),
    DeEsser(hz=6500.0, threshold_db=-32.0, ratio=4.0),
    Compressor(threshold_db=-20.0, ratio=3.0, attack_ms=8.0, release_ms=120.0, makeup_db=2.0),
    Saturation(drive=1.2, mix=0.15),
    Limiter(ceiling_db=-1.0, knee_db=3.0),
)


async def bot(runner_args: RunnerArguments) -> None:
    """Runs one session. The filter processes each output chunk."""
    transport = await create_transport(runner_args, {"webrtc": params})
    key = os.environ["OPENAI_API_KEY"]
    context = LLMContext([{"role": "system", "content": PROMPT}])
    turn = LLMUserAggregatorParams(vad_analyzer=SileroVADAnalyzer())
    aggregators = LLMContextAggregatorPair(context, user_params=turn)
    pipeline = Pipeline(
        [
            transport.input(),
            OpenAISTTService(api_key=key),
            aggregators.user(),
            OpenAILLMService(api_key=key),
            OpenAITTSService(api_key=key),
            transport.output(),
            aggregators.assistant(),
        ]
    )
    runner = WorkerRunner(handle_sigint=runner_args.handle_sigint)
    await runner.add_workers(PipelineWorker(pipeline))
    await runner.run()


def params() -> TransportParams:
    """Gives transport params with the chain on the output."""
    return TransportParams(
        audio_in_enabled=True,
        audio_out_enabled=True,
        audio_out_mixer=FilterMixer(EffectsFilter(CHAIN)),
    )


if __name__ == "__main__":
    main()
