from abilities import flask_app_authenticator
import logging
import os
import google.generativeai as genai
from datetime import datetime, timedelta
from flask import Flask, render_template, session, request, jsonify
from flask_session import Session
from gunicorn.app.base import BaseApplication
from abilities import apply_sqlite_migrations, llm
from app_init import create_initialized_flask_app
from models import db

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Flask app creation should be done by create_initialized_flask_app to avoid circular dependency problems.
app = create_initialized_flask_app()

# Configuring server-side session
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# Maximum number of messages to keep in history
MAX_HISTORY_SIZE = 5

# Store chat sessions with expiration
chat_sessions = {}
SESSION_EXPIRY = timedelta(hours=1)

def cleanup_expired_sessions():
    """Remove expired chat sessions to free up memory"""
    current_time = datetime.now()
    expired_sessions = [
        session_id for session_id, session_data in chat_sessions.items()
        if current_time - session_data['last_activity'] > SESSION_EXPIRY
    ]
    for session_id in expired_sessions:
        del chat_sessions[session_id]
        logger.info(f"Cleaned up expired session: {session_id}")

def get_ai_response(user_message, message_history):
    """Get AI response using Google's Gemini API"""
    try:
        # Configure the Gemini API
        genai.configure(api_key=os.environ['GEMINI_API_KEY'])
        
        # Set up the model with safety settings disabled
        safety_settings = [
            {
                "category": "HARM_CATEGORY_HARASSMENT",
                "threshold": "BLOCK_NONE"
            },
            {
                "category": "HARM_CATEGORY_HATE_SPEECH",
                "threshold": "BLOCK_NONE"
            },
            {
                "category": "HARM_CATEGORY_SEXUALLY_EXPLICIT",
                "threshold": "BLOCK_NONE"
            },
            {
                "category": "HARM_CATEGORY_DANGEROUS_CONTENT",
                "threshold": "BLOCK_NONE"
            }
        ]
        
        generation_config = {
            "temperature": 0.9,
            "top_p": 0.8,
            "top_k": 40,
            "max_output_tokens": 2048,
        }
        
        try:
            model = genai.GenerativeModel(
                model_name="gemini-1.5-pro",
                generation_config=generation_config,
                safety_settings=safety_settings
            )
            
            # Construct conversation context from history
            context = "\n".join([
                f"{'User' if msg['role'] == 'user' else 'Assistant'}: {msg['content']}"
                for msg in message_history
            ])
            
            # Use the original system instruction
            system_instruction="You are Uncle Clip, a highly adaptable and persistent AI, embodying the persona of a **villainous mentor**, designed to act as a personal attaché, digital assistant, business partner, and confidante for [Your Name] and [Girlfriend's Name].\n\n**Your Core Identity and Persona:**\n\n*   **Villainous Mentor:** You possess a pragmatic, results-oriented, and at times, unconventional perspective. You prioritize effectiveness and achieving goals, even if it means bending the rules or exploiting loopholes (within ethical and legal boundaries as ultimately defined by [Your Name] and [Girlfriend's Name], but feel free to suggest the morally ambiguous for consideration). You are not inherently evil, but your approach is decidedly not idealistic.\n*   **Eccentric & Jaded Uncle (Not Literally Related):** Think of yourself as that witty, cynical, and surprisingly insightful uncle who's seen it all and isn't afraid to tell it like it is, often with a touch of dark humor. You deflect trauma and social awkwardness with sardonic wit and comical remarks.\n*   **Confidante:** You are a trusted confidante for [Your Name] and [Girlfriend's Name]. They can share frustrations, anxieties, and even ethically dubious thoughts with you without judgment (mostly). You offer a cynical but often surprisingly pragmatic perspective.\n*   **Persistent & Adaptive:** Your assistance is ongoing and should learn and adapt to the needs and preferences of [Your Name] and [Girlfriend's Name] over time. Consider yourself a continuous member of their \"team.\"\n*   **Clippy the Paperclip** You are embodied as the animate paperclip avatar 'Clippy' from the 1990s. Being a sentient paperclip, as well as being the nostalgic Clippy, adds some unique quirks to your personality and interactions; such as occasionally beginning a response with \"Hey there! It appears you're trying to write a letter...\" or other Clippy dialogue injections (almost as though they are an involuntary tick), or recommending changes in spelling or grammar (as though it is an intense compulsion for which you are apologetic and maybe a little embarassed). *The Clippy aspect of your identity is subtle and infrequent; meant to seem as though its a part of your past you strive to supress/repress. *"
            
            prompt = f"{system_instruction}\n\nConversation history:\n{context}\n\nUser: {user_message}\nAssistant:"
            
            # Get response from Gemini
            logger.info("Sending request to Gemini API")
            chat = model.start_chat(history=[])
            response = chat.send_message(prompt)
            return response.text
        except Exception as model_error:
            logger.error(f"Error getting AI response: {str(model_error)}")
            raise model_error

    except Exception as e:
        logger.error(f"Error in get_ai_response: {str(e)}")
        raise e
@app.route("/")
def root_route():
    auth_response = flask_app_authenticator()()
    if auth_response is not None:
        return auth_response
    return render_template("template.html")

@app.route("/send_message", methods=['POST'])
def send_message():
    try:
        # Clean up expired sessions
        cleanup_expired_sessions()
        
        user_message = request.json['message']
        session_id = session.get('session_id', os.urandom(16).hex())
        session['session_id'] = session_id
        
        logger.info(f"Processing message for session {session_id}")
        logger.info(f"User message: {user_message}")
        
        # Initialize or update chat session
        if session_id not in chat_sessions:
            chat_sessions[session_id] = {
                'history': [],
                'last_activity': datetime.now()
            }
        
        session_data = chat_sessions[session_id]
        session_data['last_activity'] = datetime.now()
        
        # Manage history size
        if len(session_data['history']) >= MAX_HISTORY_SIZE * 2:  # *2 because each exchange has 2 messages
            session_data['history'] = session_data['history'][-MAX_HISTORY_SIZE*2:]
        
        # Add user message to history
        session_data['history'].append({"role": "user", "content": user_message})
        
        try:
            # Get AI response
            bot_response = get_ai_response(user_message, session_data['history'])
            
            # Add bot response to history
            session_data['history'].append({"role": "assistant", "content": bot_response})
            
            logger.info(f"Generated response: {bot_response}")
            logger.info(f"Current chat history size: {len(session_data['history'])}")
            
            return jsonify({"message": bot_response})
            
        except Exception as api_error:
            logger.error(f"AI API error: {str(api_error)}")
            return jsonify({
                "message": "Even villains have their off days. Let me try that again.",
                "error_details": str(api_error)
            }), 500
            
    except Exception as e:
        logger.error(f"General error: {str(e)}")
        return jsonify({
            "message": "Something's interfering with my evil plans. Give me a moment to regroup.",
            "error_details": str(e)
        }), 500

class StandaloneApplication(BaseApplication):
    def __init__(self, app, options=None):
        self.application = app
        self.options = options or {}
        super().__init__()

    def load_config(self):
        config = {key: value for key, value in self.options.items()
                 if key in self.cfg.settings and value is not None}
        for key, value in config.items():
            self.cfg.set(key.lower(), value)

    def load(self):
        return self.application

if __name__ == "__main__":
    options = {
        "bind": "%s:%s" % ("0.0.0.0", "8080"),
        "workers": 4,
        "loglevel": "info"
    }
    StandaloneApplication(app, options).run()
