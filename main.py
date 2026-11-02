"""Botkeep entry point: start command is `python main.py`."""
import asyncio

from envloader import load_env

load_env()   # must run before config / database are imported or used

from bot import main  # noqa: E402

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        pass
