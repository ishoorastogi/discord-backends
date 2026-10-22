#Resume
import processor
from shared.logs.log_config import get_logger

logger = get_logger("resume handler")

def handle_parse(event: dict):
    logger.info("Handling PARSE event")
    #TODO: Implement the logic to handle the PARSE event

def handle_extraction(event: dict):
    logger.info("Handling EXTRACTION event")
    #TODO: Implement the logic to handle the EXTRACTION event

def handle_normalization(event: dict):
    logger.info("Handling NORMALIZATION event")
    #TODO: Implement the logic to handle the NORMALIZATION event

def handle_vectorization(event: dict):
    logger.info("Handling VECTORIZATION event")
    #TODO: Implement the logic to handle the VECTORIZATION event

def handle_send_to_writer(event: dict):
    logger.info("Handling WRITE event")
    #TODO: Implement the logic to handle the WRITE event