"""
utils/cli.py — Kraken CLI subprocess helpers.

Two primitives:
    kraken_json(args)          → run `kraken <args>` and return parsed JSON
    kraken_stream_proc(args)   → start `kraken <args>` and return the proc
                                 (caller reads stdout as NDJSON)

Every call goes through the `kraken` binary installed via:
    curl --proto '=https' --tlsv1.2 -LsSf \\
      https://github.com/krakenfx/kraken-cli/releases/latest/download/kraken-cli-installer.sh | sh
"""

import asyncio
import json
import os
import shutil
from utils.logger import setup_logger

logger = setup_logger("cli")

# Allow override via env var for testing / custom installs
KRAKEN_BIN = os.environ.get("KRAKEN_BIN", "kraken")


async def kraken_json(args: list[str], timeout: float = 15.0) -> dict | list | None:
    """
    Run: kraken <args>
    Capture stdout, parse as JSON, return result.
    Returns None on error.
    """
    cmd = [KRAKEN_BIN] + args
    logger.debug(f"CLI call: {' '.join(cmd)}")
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        raw = stdout.decode("utf-8", errors="replace").strip()

        if proc.returncode != 0:
            err = stderr.decode("utf-8", errors="replace").strip()
            logger.warning(f"CLI non-zero exit {proc.returncode}: {err[:200]}")
            return None

        if not raw:
            return None

        return json.loads(raw)

    except asyncio.TimeoutError:
        logger.warning(f"CLI timeout after {timeout}s: {' '.join(args)}")
        return None
    except json.JSONDecodeError as exc:
        logger.warning(f"CLI JSON parse error: {exc} | raw={raw[:200]}")
        return None
    except Exception as exc:
        logger.error(f"CLI error: {exc}")
        return None


async def kraken_stream_proc(args: list[str]) -> asyncio.subprocess.Process:
    """
    Start: kraken <args>  (long-running streaming process)
    Returns the Process object. Caller reads proc.stdout line by line.
    stderr is discarded (diagnostics only).
    """
    cmd = [KRAKEN_BIN] + args
    logger.info(f"Spawning stream: {' '.join(cmd)}")
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.DEVNULL,
    )
    return proc
