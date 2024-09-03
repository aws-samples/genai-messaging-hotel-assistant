import json
from pathlib import Path


def get_flow_definition(knowledge_base_id: str, definition_file: Path = Path('resources/flow_definiton.json')) -> dict | list:
    """
    Auxiliary method used to obtain the flow definition
    """
    base_contents = definition_file.read_text()
    return json.loads(base_contents.replace('"${knowledge_base_id}"', f'"{knowledge_base_id}"'))
