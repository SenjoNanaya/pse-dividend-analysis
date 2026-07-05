import logging
import os
import random
import time
from dotenv import load_dotenv

load_dotenv()

LOG_FILE = os.getenv("LOG_FILE", "logs/scraper.log")
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
MIN_DELAY = float(os.getenv("MIN_DELAY", 1.5))
MAX_DELAY = float(os.getenv("MAX_DELAY", 5.5))

DEFAULT_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:152.0) Gecko/20100101 Firefox/152.0',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    'Accept-Language': 'en-US,en;q=0.9',
    'Connection': 'keep-alive',
}

def setup_logger():
    logging.basicConfig(
        level=getattr(logging, LOG_LEVEL.upper(), logging.INFO),
        format='%(asctime)s [%(levelname)s] %(message)s',
        handlers=[
            logging.FileHandler(LOG_FILE),
            logging.StreamHandler()
        ]
    )
    return logging.getLogger("PSE_Scraper")

def random_delay():
    time.sleep(random.uniform(MIN_DELAY, MAX_DELAY))

def parse_scale_factor(text):
    if not text:
        return 1
    text_lower = text.lower()
    if 'thousand' in text_lower:
        return 1000
    elif 'million' in text_lower:
        return 1_000_000
    elif 'billion' in text_lower:
        return 1_000_000_000
    else:
        return 1

logger = setup_logger()

