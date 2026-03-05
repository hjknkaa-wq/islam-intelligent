## Config Pattern

The project uses a frozen dataclass for configuration with environment variable fallbacks. Pattern:

```python
@dataclass(frozen=True)
class Settings:
    field_name: type = os.getenv("ENV_VAR", "default_value")
```

For integer fields, use the helper `_as_int()` to handle type conversion and fallback on parse errors.

Example:
```python
embedding_model: str = os.getenv("EMBEDDING_MODEL", "text-embedding-3-small")
embedding_dimension: int = _as_int(os.getenv("EMBEDDING_DIMENSION"), 1536)
```

The settings are instantiated once at module load: `settings = Settings()`
