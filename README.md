# Cognee CodGraph Local Chat Assistant

## Features

- Clean web interface using Gradio
- Conversation history persistence
- Fully local operation
- SQLite database for storing chat history
- Cognee Background with Knowledge Graphs and different agent types.(Summary, Chunks, Completion, Insights)

## Installation

0. Install [Cognee](https://github.com/topoteretes/cognee) in server mode

1. Clone the repository
```bash
git clone [your-repo-url]
```

2. Create and activate a virtual environment
```bash
python -m venv .venv
source .venv/bin/activate  # On Windows use: .venv\Scripts\activate
```

3. Install dependencies
```bash
pip install -r requirements.txt
```
Create a .env file in the root directory and add your configuration.

4. Usage
Run the application:
```bash
python main.py
```

The web interface will be available at http://localhost:7860
