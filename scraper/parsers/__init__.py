"""Parser registry and imports."""

from .base_parser import BaseParser, ParsedResult
from .milesplit_multi import MilesplitMultiParser
from .milesplit_single import MilesplitSingleParser
from .milesplit_text import MilesplitTextParser
from .milesplit_web import MilesplitWebParser
from .generic_table import GenericTableParser
from .hytek_text import HyTekTextParser

# Registry of available parsers.
# milesplit_web is listed first so it wins can_parse detection for scraped JSON files.
PARSERS = {
    'milesplit_web': MilesplitWebParser(),
    'milesplit_multi': MilesplitMultiParser(),
    'milesplit_single': MilesplitSingleParser(),
    'milesplit_text': MilesplitTextParser(),
    'generic_table': GenericTableParser(),
    'hytek_text': HyTekTextParser(),
}


def get_parser(name: str) -> BaseParser:
    """Get a parser by name."""
    if name not in PARSERS:
        raise ValueError(f"Unknown parser: {name}. Available: {list(PARSERS.keys())}")
    return PARSERS[name]


__all__ = [
    'BaseParser',
    'ParsedResult',
    'MilesplitMultiParser',
    'MilesplitSingleParser',
    'MilesplitTextParser',
    'MilesplitWebParser',
    'GenericTableParser',
    'HyTekTextParser',
    'get_parser',
    'PARSERS',
]
