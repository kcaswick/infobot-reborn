# Infobot Reborn Architecture

## Overview
Infobot Reborn is an LLM-powered conversational AI chatbot, designed as a spiritual successor to the original Infobot project. The application is built with Python and designed for serverless deployment on Modal.

## Design Principles
- **Hosting Agnostic**: Core logic remains independent of deployment environment
- **Serverless First**: Optimized for serverless deployment (Modal)
- **Modular Design**: Components are decoupled for easy testing and extension
- **Stateless Operation**: Persistence handled via external services

## Core Components

### Message Handler
- Processes incoming messages
- Routes to appropriate modules based on intent
- Maintains conversation context

### LLM Service
- Abstraction over LLM providers
- Handles prompt engineering and response formatting
- Manages token usage and rate limiting

### Knowledge Base
- Stores and retrieves factual information
- Handles information updating and validation
- Provides context for LLM responses

### Conversation Manager
- Tracks conversation state
- Manages user preferences and history
- Provides context for personalized responses

### Plugin System
- Extensible framework for custom functionality
- Standard interface for third-party integrations
- Discovery and registration mechanism

## Deployment Architecture
- **Local Development**: Run with standard Python
- **Serverless Deployment**: Modal for production deployment
- **Modal Integration**: Contained in `modal.py` with minimal dependencies on Modal-specific features

## Data Flow
1. User message received via API endpoint
2. Message Handler processes and classifies the message
3. Request routed to appropriate components
4. LLM generates response with context from Knowledge Base
5. Response sent back to user
6. Conversation state updated

## Future Extensions
- Multi-modal input/output (images, audio)
- Fine-tuning capabilities
- Advanced retrieval augmented generation (RAG)
- User authentication and personalization