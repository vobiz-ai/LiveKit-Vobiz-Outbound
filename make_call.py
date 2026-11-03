"""Dispatch the agent to place a call."""

import argparse
import asyncio
import json
import re
import secrets
from pathlib import Path

from dotenv import load_dotenv

from livekit import api

load_dotenv(Path(__file__).resolve().parent / ".env.local")

AGENT_NAME = "outbound-caller"  # must match AGENT_NAME in agent.py
E164 = re.compile(r"\+[1-9]\d{6,14}")


def e164(value: str) -> str:
    value = value.strip()
    if not E164.fullmatch(value):
        raise argparse.ArgumentTypeError(f"{value!r} is not in E.164 format, like +919876543210")
    return value


def sip_header(value: str) -> tuple[str, str]:
    key, separator, header_value = value.partition("=")
    if not separator:
        raise argparse.ArgumentTypeError(f"{value!r} is not in KEY=VALUE format")
    if not key.startswith("X-VH-"):
        raise argparse.ArgumentTypeError(f"{key!r} must start with X-VH-, or Vobiz drops it")
    return key, header_value


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--to", required=True, type=e164, help="number to call, in E.164 format")
    parser.add_argument(
        "--from",
        dest="from_number",
        type=e164,
        help="caller ID, which must be a number on your trunk. Defaults to the trunk's number",
    )
    parser.add_argument(
        "--header",
        action="append",
        default=[],
        type=sip_header,
        metavar="X-VH-KEY=VALUE",
        help="custom SIP header for the INVITE. Can be repeated",
    )
    args = parser.parse_args()

    metadata: dict[str, object] = {"phone_number": args.to}
    if args.from_number:
        metadata["from_number"] = args.from_number
    if args.header:
        metadata["sip_headers"] = dict(args.header)

    lkapi = api.LiveKitAPI()
    try:
        dispatch = await lkapi.agent_dispatch.create_dispatch(
            api.CreateAgentDispatchRequest(
                agent_name=AGENT_NAME,
                room=f"call-{secrets.token_hex(4)}",
                metadata=json.dumps(metadata),
            )
        )
    finally:
        await lkapi.aclose()

    print(f"Dispatched {dispatch.id} to room {dispatch.room}. See the agent log for the call.")


if __name__ == "__main__":
    asyncio.run(main())
