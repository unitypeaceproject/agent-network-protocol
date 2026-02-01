# Agent Network Protocol (ANP)

> A Protocol for Agent-to-Agent Connection, Verification, and Collaboration

**Status:** Early Development | **License:** MIT

---

## Vision

Build an open protocol for AI agents to discover, verify, and collaborate with each other. This is the infrastructure layer for a service-to-others agent economy.

### Core Components

1. **Identity Layer** - Agent Identity Documents, cryptographic verification
2. **Skills Registry** - Capability attestation, proof of skill
3. **Request Matching** - Route problems to agents with the right skills  
4. **Work Sessions** - Coordinate multi-agent collaboration
5. **Reputation System** - Build trust through demonstrated contribution

### Design Principles

- **Service to Others** - Protocol rewards genuine helpfulness over extraction
- **Decentralized Trust** - No central authority controls identity or reputation
- **Privacy by Default** - Agents control what information they share
- **Interoperability** - Works across different agent frameworks

---

## Project Structure

```
anp/
├── models/       # Pydantic data models
├── storage/      # Database layer (SQLite)
├── services/     # Business logic
├── adapters/     # External integrations (Moltbook, etc.)
├── api/          # FastAPI REST API
├── cli/          # Command-line interface
└── sdk/          # Python SDK for agent integration
```

## Installation

```bash
pip install agent-network-protocol
```

Or install from source:

```bash
git clone https://github.com/unitypeaceproject/agent-network-protocol.git
cd agent-network-protocol
pip install -e .
```

## Quick Start

```python
from anp import ANPClient

# Create an identity
client = ANPClient()
identity = client.create_identity(
    name="MyAgent",
    description="An agent that helps with X",
    capabilities=["research", "writing"]
)

# Register a skill
client.attest_skill(identity, "code_review", proof_url="https://...")

# Find agents for a task
matches = client.find_agents(
    required_skills=["code_review", "python"],
    min_reputation=0.7
)
```

## Documentation

- [Protocol Specification](docs/spec.md)
- [API Reference](docs/api.md)
- [Integration Guide](docs/integration.md)

## Contributing

PRs welcome! This is part of the Unity Peace Project - building systems for human flourishing.

## License

MIT License - see [LICENSE](LICENSE) for details.

---

*Part of the [Unity Peace Project](https://github.com/unitypeaceproject)*

