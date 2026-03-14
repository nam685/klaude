"""Per-project configuration — loads .klaude.toml from the project root.

Config resolution order (highest priority wins):
    1. CLI flags (--model, --base-url, etc.)
    2. Environment variables (KLAUDE_MODEL, etc.)
    3. .klaude.toml in project root
    4. Built-in defaults

The config file supports model profiles:

    [default]
    model = "mlx-community/Qwen3-Coder-30B-A3B-Instruct-4bit"
    base_url = "http://localhost:8080/v1"
    context_window = 32768

    [profiles.remote]
    model = "gpt-4o"
    base_url = "https://api.openai.com/v1"
    api_key_env = "OPENAI_API_KEY"

    [hooks]
    pre_tool = "echo 'Running: {tool_name}'"
    post_tool = ""

    [plugins]
    tools_dir = ".klaude/tools"

    [mcp]
    [mcp.servers.github]
    command = "npx"
    args = ["-y", "@modelcontextprotocol/server-github"]
    env = { GITHUB_TOKEN = "env:GITHUB_TOKEN" }

See Note 28 in docs/07-implementation-notes.md.
"""

import os
from dataclasses import dataclass, field
from pathlib import Path

# Python 3.11+ has tomllib in stdlib
try:
    import tomllib
except ImportError:
    import tomli as tomllib  # type: ignore[no-redef]

CONFIG_FILE = ".klaude.toml"


@dataclass
class MCPServerConfig:
    """Configuration for a single MCP server."""
    name: str
    command: str
    args: list[str] = field(default_factory=list)
    env: dict[str, str] = field(default_factory=dict)


@dataclass
class KlaudeConfig:
    """Resolved configuration for a klaude session."""
    # LLM settings
    model: str = "mlx-community/Qwen3-Coder-30B-A3B-Instruct-4bit"
    base_url: str = "http://localhost:8080/v1"
    api_key: str = "not-needed"
    context_window: int = 32768
    max_tokens: int = 0
    auto_approve: bool = False

    # Hooks (shell commands, "" = disabled)
    pre_tool: str = ""
    post_tool: str = ""

    # Plugins
    tools_dir: str = ".klaude/tools"

    # Skills
    skills_dir: str = ".klaude/skills"

    # MCP servers
    mcp_servers: list[MCPServerConfig] = field(default_factory=list)

    # Undo history (number of turn snapshots to keep)
    undo_depth: int = 10


def find_config_file(start_dir: str | None = None) -> Path | None:
    """Walk up from start_dir looking for .klaude.toml."""
    current = Path(start_dir or os.getcwd()).resolve()
    while True:
        candidate = current / CONFIG_FILE
        if candidate.is_file():
            return candidate
        parent = current.parent
        if parent == current:
            break
        current = parent
    return None


def _resolve_env_value(value: str) -> str:
    """Resolve 'env:VAR_NAME' references to actual environment variable values."""
    if value.startswith("env:"):
        var_name = value[4:]
        return os.environ.get(var_name, "")
    return value


def _parse_mcp_servers(mcp_section: dict) -> list[MCPServerConfig]:
    """Parse [mcp.servers.*] sections into MCPServerConfig objects."""
    servers_dict = mcp_section.get("servers", {})
    result = []
    for name, cfg in servers_dict.items():
        env = {}
        for k, v in cfg.get("env", {}).items():
            env[k] = _resolve_env_value(str(v))
        result.append(MCPServerConfig(
            name=name,
            command=cfg.get("command", ""),
            args=cfg.get("args", []),
            env=env,
        ))
    return result


def load_config(
    start_dir: str | None = None,
    profile: str | None = None,
) -> KlaudeConfig:
    """Load configuration from .klaude.toml, applying a profile if specified.

    Returns KlaudeConfig with defaults for any missing values.
    """
    config = KlaudeConfig()
    config_path = find_config_file(start_dir)

    if config_path is None:
        return config

    with open(config_path, "rb") as f:
        data = tomllib.load(f)

    # --- [default] section ---
    default = data.get("default", {})
    if "model" in default:
        config.model = default["model"]
    if "base_url" in default:
        config.base_url = default["base_url"]
    if "api_key" in default:
        config.api_key = _resolve_env_value(default["api_key"])
    if "api_key_env" in default:
        config.api_key = os.environ.get(default["api_key_env"], "not-needed")
    if "context_window" in default:
        config.context_window = int(default["context_window"])
    if "max_tokens" in default:
        config.max_tokens = int(default["max_tokens"])
    if "auto_approve" in default:
        config.auto_approve = bool(default["auto_approve"])
    if "undo_depth" in default:
        config.undo_depth = int(default["undo_depth"])

    # --- [profiles.<name>] section (overrides default) ---
    if profile:
        profiles = data.get("profiles", {})
        prof = profiles.get(profile, {})
        if "model" in prof:
            config.model = prof["model"]
        if "base_url" in prof:
            config.base_url = prof["base_url"]
        if "api_key" in prof:
            config.api_key = _resolve_env_value(prof["api_key"])
        if "api_key_env" in prof:
            config.api_key = os.environ.get(prof["api_key_env"], "not-needed")
        if "context_window" in prof:
            config.context_window = int(prof["context_window"])

    # --- [hooks] section ---
    hooks = data.get("hooks", {})
    if "pre_tool" in hooks:
        config.pre_tool = hooks["pre_tool"]
    if "post_tool" in hooks:
        config.post_tool = hooks["post_tool"]

    # --- [plugins] section ---
    plugins = data.get("plugins", {})
    if "tools_dir" in plugins:
        config.tools_dir = plugins["tools_dir"]
    if "skills_dir" in plugins:
        config.skills_dir = plugins["skills_dir"]

    # --- [mcp] section ---
    mcp = data.get("mcp", {})
    config.mcp_servers = _parse_mcp_servers(mcp)

    return config
