# Infobot Reborn Architecture

## Overview
Infobot Reborn is an LLM-powered conversational AI chatbot, designed as a spiritual successor to the original Infobot project. The application is built with Python and designed for serverless deployment on Modal.

## Design Principles
- **Hosting Agnostic**: Core logic remains independent of deployment environment
- **Serverless First**: Optimized for serverless deployment (Modal)
- **Modular Design**: Components are decoupled for easy testing and extension
- **Stateless Operation**: Persistence handled via SQLite on Modal Volumes
- **OpenAI-Compatible Interface**: All LLM access goes through the OpenAI client protocol, making providers swappable via base URL

## Core Components

### Message Handler
- Processes incoming messages from chat platforms
- Routes to appropriate modules based on intent
- Maintains conversation context

### LLM Service
- OpenAI-compatible client interface (works with vLLM, ollama, cloud APIs)
- Handles prompt engineering and response formatting
- Manages token usage and rate limiting
- Default implementation uses vLLM serving locally-hosted open-source LLMs
- Supports customization via prompt engineering and fine-tuning

### Knowledge Base
- Stores and retrieves factual information in SQLite
- Handles information updating and validation
- Provides context for LLM responses
- Supports legacy Infobot factoid import

### Conversation Manager
- Tracks conversation state
- Manages user preferences and history
- Provides context for personalized responses

### Plugin System (Phase 4)
- Extensible framework for custom functionality
- Standard interface for third-party integrations
- Discovery and registration mechanism

## Chat Platform Integration

### Primary: Discord
- Discord bot using discord.py
- Slash commands and natural message handling
- Guild/channel-aware factoid scoping

### Future: Other Platforms
- Telegram, Facebook Messenger as nice-to-haves
- Platform adapters implement a common interface
- Core logic is platform-agnostic

## Deployment Architecture
- **Local Development**: Run with standard Python + ollama for LLM inference
- **Serverless Deployment**: Modal for production deployment
- **Modal Integration**: Contained in `modal.py` with minimal dependencies on Modal-specific features

## Data Flow
1. User message received via Discord (or other chat platform)
2. Message Handler processes and classifies the message
3. Request routed to appropriate components
4. LLM generates response with context from Knowledge Base
5. Response sent back to user
6. Conversation state updated

## Database Strategy

### SQLite
- Modern equivalent to the Berkeley DB the original Infobot used
- Factoid storage, karma, user data
- Stored on Modal Volumes for persistence

### Concurrency on Modal
- Single-writer constraint: each SQLite database file accessed by one instance only
- For multi-instance scaling: use Modal's distributed mechanisms (modal.Dict) for coordination
- WAL mode for better read concurrency where applicable

## LLM Strategy

### Default Approach
- Use locally-hosted open-source LLMs via vLLM
- Current default model: Qwen3-4B-Instruct (Q4_K quantization)
- Smaller models (0.6B-1.5B) available for faster responses or testing
- All access via OpenAI-compatible API (vLLM in production, ollama in dev)
- Custom prompt templates to match infobot's conversational style

### Performance Targets
- Response latency should feel like human typing speed (~2-4 seconds)
- On Modal T4: Qwen3-4B Q4_K achieves ~60 tok/s (well above human reading speed)
- Smaller models (0.6B) achieve ~180 tok/s for latency-critical paths
- Time-to-first-token is the key latency metric to optimize

### Local Development
- CPU-only inference supported for environments without GPU
- Smaller/faster models recommended for test suites
- Ollama as the local inference server (OpenAI-compatible endpoint)

### Fine-tuning Pipeline
- Initial alignment via prompt engineering
- Reinforcement Learning (RL) with LoRA for deeper behavioral alignment
- Training data sourced from:
  - Historical infobot conversation logs
  - Synthetic training examples
- All training data published under CC-BY license
- Open-source training scripts for customization

### Model Customization
- End users can substitute preferred base models
- Documentation for adapting the system to different LLMs
- Evaluation framework to assess behavioral alignment

## Future Extensions
- Additional chat platforms (Telegram, Facebook Messenger)
- Multi-modal input/output (images, audio)
- Advanced retrieval augmented generation (RAG)
- User authentication and personalization
- Additional fine-tuning techniques beyond RL-LoRA
