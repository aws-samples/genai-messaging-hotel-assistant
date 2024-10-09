import json
from pathlib import Path


def get_flow_definition(definition_file: Path,
                        knowledge_base_id: str,
                        spa_availability_lambda_arn: str) -> dict | list:
    """
    Auxiliary method used to obtain the flow definition
    """
    base_contents = definition_file.read_text()
    return json.loads(base_contents.
                      replace('"{{KNOWLEDGE_BASE_ID}}"', f'"{knowledge_base_id}"').
                      replace('"{{SPA_AVAILABILITY_LAMBDA_ARN}}"', f'"{spa_availability_lambda_arn}"'))
