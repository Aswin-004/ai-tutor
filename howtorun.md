# How to Run the AI Tutor API

## Prerequisites
- Python 3.8+
- API Keys for Jina AI and Google Gemini

## Setup Instructions

1. **Navigate to the project directory**:
   If you're on WSL or Linux/macOS:
   ```bash
   cd ~/projects/test
   ```

2. **Create a virtual environment (recommended)**:
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows use `venv\Scripts\activate`
   ```

3. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

4. **Environment Variables Config**:
   Create a `.env` file in the root directory (`~/projects/test/.env`) and add the following keys:
   ```env
   JINA_API_KEY=your_jina_api_key_here
   GOOGLE_API_KEY=your_google_api_key_here
   SECRET_KEY=your_super_secret_jwt_key
   ALGORITHM=HS256
   ACCESS_TOKEN_EXPIRE_MINUTES=1440
   ```
   *(Note: `JINA_API_KEY` and `GOOGLE_API_KEY` are mandatory as per `core.py`)*

## Running the Application

1. **Start the FastAPI server**:
   From within the `~/projects/test` directory (with your virtual environment active):
   ```bash
   uvicorn app:app --reload
   ```

2. **Access the Application**:
   - The frontend interface is available at: [http://127.0.0.1:8000/](http://127.0.0.1:8000/)
   - The interactive API documentation (Swagger UI) is available at: [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)

## Application Features
- **User Authentication:** Registration, login, and JWT-based session management.
- **PDF Document Upload:** Upload PDFs for automated text extraction and vector chunking using Jina AI embeddings and ChromaDB.
- **AI Tutor Chat:** Context-aware learning assistant utilizing Gemini 2.5 Flash and RAG (Retrieval-Augmented Generation) based on the user's uploaded modules.
- **Roadmap Generation:** Personalized learning path creation.
