"""
Prompt management for AI operations.
"""

import yaml
import os
from typing import Dict, Any, Optional
from pathlib import Path


class PromptLoader:
    """Load and manage prompt templates from YAML files."""
    
    def __init__(self, prompts_dir: str = "prompts"):
        """Initialize prompt loader with directory."""
        self.prompts_dir = Path(prompts_dir)
        self._cache = {}
    
    def load_prompt(self, prompt_name: str) -> Dict[str, Any]:
        """Load prompt template from YAML file."""
        if prompt_name in self._cache:
            return self._cache[prompt_name]
        
        prompt_file = self.prompts_dir / f"{prompt_name}.yaml"
        if not prompt_file.exists():
            raise FileNotFoundError(f"Prompt file not found: {prompt_file}")
        
        with open(prompt_file, 'r') as f:
            prompt_data = yaml.safe_load(f)
        
        self._cache[prompt_name] = prompt_data
        return prompt_data
    
    def format_prompt(self, prompt_name: str, **kwargs) -> str:
        """Format prompt template with variables."""
        prompt_data = self.load_prompt(prompt_name)
        prompt_template = prompt_data.get("prompt", "")
        
        # Replace variables in template
        formatted_prompt = prompt_template
        for key, value in kwargs.items():
            placeholder = f"<{key}>"
            formatted_prompt = formatted_prompt.replace(placeholder, str(value))
        
        return formatted_prompt
    
    def get_categories(self, prompt_name: str = "text_analysis") -> list:
        """Get available categories from prompt template."""
        prompt_data = self.load_prompt(prompt_name)
        return prompt_data.get("variables", {}).get("categories", [])
    
    def reload_prompt(self, prompt_name: str):
        """Reload prompt from file (clear cache)."""
        if prompt_name in self._cache:
            del self._cache[prompt_name]
        return self.load_prompt(prompt_name)


# Global prompt loader instance
prompt_loader = PromptLoader()
