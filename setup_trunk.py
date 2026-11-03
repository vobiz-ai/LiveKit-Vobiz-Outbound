"""Create the LiveKit outbound trunk for Vobiz, or update it if SIP_OUTBOUND_TRUNK_ID is set."""

import asyncio
import os
from pathlib import Path

from dotenv import load_dotenv

from livekit import api

load_dotenv(Path(__file__).resolve().parent / ".env.local")


def require_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise SystemExit(f"{name} is not set in .env.local")
    return value


async def main() -> None:
    address = require_env("VOBIZ_SIP_DOMAIN")
    username = require_env("VOBIZ_USERNAME")
    password = require_env("VOBIZ_PASSWORD")
    number = require_env("VOBIZ_OUTBOUND_NUMBER")
    trunk_id = os.getenv("SIP_OUTBOUND_TRUNK_ID")

    lkapi = api.LiveKitAPI()
    try:
        if trunk_id:
            await lkapi.sip.update_outbound_trunk_fields(
                trunk_id,
                address=address,
                auth_username=username,
                auth_password=password,
                numbers=[number],
            )
            print(f"Updated outbound trunk {trunk_id}")
            return

        trunk = await lkapi.sip.create_outbound_trunk(
            api.CreateSIPOutboundTrunkRequest(
                trunk=api.SIPOutboundTrunkInfo(
                    name="Vobiz outbound",
                    address=address,
                    numbers=[number],
                    auth_username=username,
                    auth_password=password,
                )
            )
        )
        print(f"Created outbound trunk {trunk.sip_trunk_id}")
        print(f"Add this to .env.local: SIP_OUTBOUND_TRUNK_ID={trunk.sip_trunk_id}")
    finally:
        await lkapi.aclose()


if __name__ == "__main__":
    asyncio.run(main())
