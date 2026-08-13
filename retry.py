import logging
import os
import time

_LOG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "pipeline.log")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(_LOG_PATH),
    ],
)
logger = logging.getLogger(__name__)


def with_retry(fn, *args, max_attempts=3, backoff_seconds=2, **kwargs):
    for attempt in range(1, max_attempts + 1):
        try:
            return fn(*args, **kwargs)
        except Exception as e:
            logger.warning(f"{fn.__name__} failed on attempt {attempt}/{max_attempts}: {e}")
            if attempt == max_attempts:
                logger.error(f"{fn.__name__} failed after {max_attempts} attempts, giving up.")
                raise
            time.sleep(backoff_seconds * (2 ** (attempt - 1)))
