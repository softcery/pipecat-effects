"""One voice bot with a chain on its output. Run it with the pipecat runner.

It needs pipecat-ai[runner,webrtc,openai,silero] and OPENAI_API_KEY. --chain picks one of the
4 README chains. --bypass runs the session with the chain off. The chain runs as the output
filter. A chain with Reverb runs in FilterMixer, so its tail rings out after each turn. --meter
runs any chain in FilterMixer, and the log gives the loudness and the true peak of each bot turn.
"""

import argparse
import os

from loguru import logger
from pipecat.audio.vad.silero import SileroVADAnalyzer
from pipecat.frames.frames import FilterEnableFrame, MixerEnableFrame
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
from pipecat.services.openai.stt import OpenAIRealtimeSTTService
from pipecat.services.openai.tts import OpenAITTSService
from pipecat.transports.base_transport import TransportParams
from pipecat.workers.runner import WorkerRunner

from chains import CHAINS
from pipecat_effects import Effects, EffectsFilter, FilterMixer, Reverb

PROMPT = "You are a voice assistant. Answer in one short sentence."
CHANNELS = 1
CHAIN = "eq-compression"  # the default of --chain
LLM = "gpt-4.1-mini"


async def bot(runner_args: RunnerArguments) -> None:
    """Runs one session. The filter processes each output chunk."""
    args = runner_args.cli_args or argparse.Namespace(chain=CHAIN, bypass=False, meter=False)
    chain = CHAINS[args.chain]
    effects = EffectsFilter(chain)
    mixer = FilterMixer(effects, channels=CHANNELS) if args.meter or _tailed(chain) else None
    transport = await create_transport(runner_args, {"webrtc": lambda: params(effects, mixer)})
    key = os.environ["OPENAI_API_KEY"]
    context = LLMContext([{"role": "system", "content": PROMPT}])
    turn = LLMUserAggregatorParams(vad_analyzer=SileroVADAnalyzer())
    aggregators = LLMContextAggregatorPair(context, user_params=turn)
    pipeline = Pipeline(
        [
            transport.input(),
            OpenAIRealtimeSTTService(api_key=key),
            aggregators.user(),
            OpenAILLMService(api_key=key, settings=OpenAILLMService.Settings(model=LLM)),
            OpenAITTSService(api_key=key),
            transport.output(),
            aggregators.assistant(),
        ]
    )
    worker = PipelineWorker(pipeline)
    if mixer is not None and args.meter and worker.turn_tracking_observer is not None:
        worker.turn_tracking_observer.add_event_handler("on_turn_ended", _metered(mixer))
    runner = WorkerRunner(handle_sigint=runner_args.handle_sigint)
    await runner.add_workers(worker)
    if args.bypass:
        bypass = FilterEnableFrame if mixer is None else MixerEnableFrame
        await worker.queue_frame(bypass(enable=False))
    await runner.run()


def params(effects: EffectsFilter, mixer: FilterMixer | None) -> TransportParams:
    """Gives transport params with the chain on the output, in the mixer if there is one."""
    return TransportParams(
        audio_in_enabled=True,
        audio_out_enabled=True,
        audio_out_channels=CHANNELS,
        audio_out_filter=effects if mixer is None else None,
        audio_out_mixer=mixer,
    )


def _tailed(chain: Effects) -> bool:
    """Tells whether the chain holds a Reverb, whose tail needs the silence a mixer gives."""
    return any(isinstance(effect, Reverb) for effect in chain)


def _metered(mixer: FilterMixer):
    """Gives one handler that logs the reading of each bot turn."""

    async def ended(observer: object, turn: int, duration: float, interrupted: bool) -> None:
        reading = mixer.read()
        if reading is None:
            logger.info(f"turn {turn}: silence")
        else:
            logger.info(f"turn {turn}: {reading.lufs:.1f} LUFS, {reading.dbtp:.1f} dBTP")

    return ended


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--chain", choices=CHAINS, default=CHAIN, help="the chain")
    parser.add_argument("--bypass", action="store_true", help="run with the chain off")
    parser.add_argument("--meter", action="store_true", help="run in FilterMixer, log each turn")
    main(parser)
