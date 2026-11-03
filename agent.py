"""Place outbound calls over a Vobiz SIP trunk with a LiveKit voice agent."""

import json
import logging
import os
from pathlib import Path

from dotenv import load_dotenv
from google.protobuf.duration_pb2 import Duration

from livekit import api
from livekit.agents import (
    Agent,
    AgentServer,
    AgentSession,
    JobContext,
    TurnHandlingOptions,
    cli,
    inference,
)
from livekit.agents.beta import EndCallTool
from livekit.protocol import sip as sip_protocol

load_dotenv(Path(__file__).resolve().parent / ".env.local")

logger = logging.getLogger("vobiz-outbound")

# Must match AGENT_NAME in make_call.py.
AGENT_NAME = "outbound-caller"
PARTICIPANT_IDENTITY = "phone-user"
RINGING_TIMEOUT_SECONDS = 45


class OutboundAssistant(Agent):
    def __init__(self) -> None:
        super().__init__(
            instructions=(
                "You are a voice AI assistant on an outbound phone call. "
                "Say who you are when the person answers, and say you are an AI assistant if "
                "you are asked. Keep replies to one or two short sentences, and do not use "
                "lists, markdown or emojis. "
                "When the person is finished, say goodbye and end the call."
            ),
            tools=[EndCallTool()],
        )


server = AgentServer()


@server.rtc_session(agent_name=AGENT_NAME)
async def entrypoint(ctx: JobContext) -> None:
    ctx.log_context_fields = {"room": ctx.room.name}

    # make_call.py puts the call details in the dispatch metadata.
    metadata = json.loads(ctx.job.metadata)

    session: AgentSession = AgentSession(
        stt=inference.STT("deepgram/nova-3", language="multi"),
        llm=inference.LLM("openai/gpt-4.1-mini"),
        tts=inference.TTS("cartesia/sonic-3", voice="9626c31c-bec5-4cca-baa8-f8ba9e84c8bc"),
        turn_handling=TurnHandlingOptions(turn_detection=inference.TurnDetector()),
    )

    async def hangup() -> None:
        # Deleting the room ends the phone call for the SIP participant.
        await ctx.api.room.delete_room(api.DeleteRoomRequest(room=ctx.room.name))

    ctx.add_shutdown_callback(hangup)

    # Start the session first so none of the callee's audio is lost after they answer.
    await session.start(agent=OutboundAssistant(), room=ctx.room)
    if not session.room_io:
        raise RuntimeError("room_io is unavailable, use the dev or start command")
    session.room_io.set_participant(PARTICIPANT_IDENTITY)

    try:
        await ctx.api.sip.create_sip_participant(
            api.CreateSIPParticipantRequest(
                room_name=ctx.room.name,
                sip_trunk_id=os.environ["SIP_OUTBOUND_TRUNK_ID"],
                sip_call_to=metadata["phone_number"],
                sip_number=metadata.get("from_number", ""),
                participant_identity=PARTICIPANT_IDENTITY,
                headers=metadata.get("sip_headers", {}),
                include_headers=sip_protocol.SIP_X_HEADERS,
                krisp_enabled=True,
                ringing_timeout=Duration(seconds=RINGING_TIMEOUT_SECONDS),
                wait_until_answered=True,
            )
        )
    except api.TwirpError as e:
        # Covers rejected calls and calls that ring out without an answer.
        logger.warning(f"call did not connect: {e.message}")
        ctx.shutdown("call did not connect")
        return

    # sip.callIDFull identifies this call in the Vobiz CDR, so log it to join the two records.
    callee = ctx.room.remote_participants.get(PARTICIPANT_IDENTITY)
    call_id = callee.attributes.get("sip.callIDFull") if callee else None
    logger.info("call answered", extra={"sip_call_id": call_id})

    # The agent waits for the callee to say hello. To speak first, call session.generate_reply().


if __name__ == "__main__":
    cli.run_app(server)
