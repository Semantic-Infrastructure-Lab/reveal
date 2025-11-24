"""Sample Python file for validation testing."""

import os
import sys
from typing import Dict, List, Optional
from pathlib import Path

# Module-level constant
DEFAULT_CONFIG_PATH = "/etc/config.json"

def load_config(path: str) -> Dict[str, any]:
    """Load configuration from JSON file.
    
    Args:
        path: Path to config file
        
    Returns:
        Dictionary of configuration values
    """
    with open(path) as f:
        return json.load(f)

def process_items(items: List[str], *, uppercase: bool = False) -> List[str]:
    """Process a list of items.
    
    Args:
        items: List of strings to process
        uppercase: Whether to convert to uppercase
        
    Returns:
        Processed list of items
    """
    if uppercase:
        return [item.upper() for item in items]
    return [item.lower() for item in items]

class DataProcessor:
    """Main data processing class.
    
    Handles data transformation and validation.
    """
    
    def __init__(self, config: Dict[str, any]):
        """Initialize processor with configuration.
        
        Args:
            config: Configuration dictionary
        """
        self.config = config
        self._cache = {}
    
    def transform(self, data: str) -> str:
        """Transform data according to configuration.
        
        Args:
            data: Input data string
            
        Returns:
            Transformed data
        """
        return data.lower().strip()
    
    async def async_process(self, items: List[str]) -> List[str]:
        """Process items asynchronously.
        
        Args:
            items: Items to process
            
        Returns:
            Processed items
        """
        return [await self._process_one(item) for item in items]

def main():
    """Main entry point."""
    config = load_config(DEFAULT_CONFIG_PATH)
    processor = DataProcessor(config)
    print("Ready!")

if __name__ == '__main__':
    main()
