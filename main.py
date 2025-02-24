from flask import Flask, render_template, request, redirect, url_for, session, jsonify, flash
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
import os
from langchain_ollama import OllamaLLM
from langchain_core.prompts import ChatPromptTemplate
from datetime import datetime
from flask_migrate import Migrate

# Initialize Flask app
app = Flask(__name__)
app.config["SECRET_KEY"] = "your_secret_key"
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///users.db"
app.config["UPLOAD_FOLDER"] = "uploads"
os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)

# Initialize the database and migration
db = SQLAlchemy(app)
migrate = Migrate(app, db)

# Admin Credentials
ADMIN_USERNAME = "admin"
ADMIN_PASSWORD_HASH = generate_password_hash("adminpassword", method="pbkdf2:sha256")

# User Model
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)  # Track registration date

# AI Model Setup
template = """
You are a helpful and friendly AI assistant. Your goal is to assist users with their questions and tasks in a clear and concise manner. Be polite, professional, and provide accurate information.

Here is the conversation history: {context}

Question: {question}

Answer:
"""
model = OllamaLLM(model="llama3.2:latest")
prompt = ChatPromptTemplate.from_template(template)
chain = prompt | model

# Home Page Route
@app.route("/")
def home():
    return render_template("home.html")

# About Page Route
@app.route("/about")
def about():
    return render_template("about.html")

# Login Route
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]
        
        if username == ADMIN_USERNAME and check_password_hash(ADMIN_PASSWORD_HASH, password):
            session["admin"] = username
            return redirect(url_for("admin"))
        
        user = User.query.filter_by(username=username).first()
        if user and check_password_hash(user.password, password):
            session["user"] = username
            flash("Login successful!", "success")
            return redirect(url_for("chat_page"))
        else:
            flash("Invalid credentials. Try again.", "danger")
    
    return render_template("login.html")

# Registration Route
@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]
        hashed_password = generate_password_hash(password, method="pbkdf2:sha256")
        
        if User.query.filter_by(username=username).first():
            flash("Username already exists. Try another one.", "danger")
            return redirect(url_for("register"))

        new_user = User(username=username, password=hashed_password)
        db.session.add(new_user)
        db.session.commit()
        flash("Registration successful! You can now log in.", "success")
        return redirect(url_for("login"))
    return render_template("register.html")

# Logout Route
@app.route("/logout")
def logout():
    session.pop("user", None)
    session.pop("admin", None)
    flash("You have been logged out.", "info")
    return redirect(url_for("login"))

# Forgot Password Route
@app.route("/forgot-password", methods=["GET", "POST"])
def forgot_password():
    if request.method == "POST":
        username = request.form.get("username")
        new_password = request.form.get("new_password")
        
        if not new_password:
            flash("New password is required.", "danger")
            return render_template("forgot_password.html")

        user = User.query.filter_by(username=username).first()
        if user:
            user.password = generate_password_hash(new_password, method="pbkdf2:sha256")
            db.session.commit()
            flash("Password reset successful. You can now log in.", "success")
            return redirect(url_for("login"))
        else:
            flash("User not found.", "danger")
    return render_template("forgot_password.html")

# Chat Route
@app.route("/chat", methods=["GET", "POST"])
def chat_page():
    if "user" not in session:
        flash("You need to log in to access the chat.", "warning")
        return redirect(url_for("login"))

    # Initialize or retrieve the user's conversation context
    if "context" not in session:
        session["context"] = ""  # Reset context for a new conversation

    if request.method == "POST":
        user_input = request.json.get("message")
        print(f"User input: {user_input}")  # Debugging statement

        # Preprocess the input to expand shortcuts
        user_input = expand_shortcuts(user_input)

        # Check if the user is asking "Who created you?"
        if user_input.lower().strip() in ["who created you?", "who made you?", "who developed you?", "who created u?", "who made u?", "who developed u?"]:
            response = (
                "Saif Al Harthi and Jumana Al Mahruqi created me! "
                "You created me, as I'm an artificial intelligence language model designed to assist with questions and tasks using the two primary use cases: Customer Service and Educational Support."
            )
            return jsonify({"response": response})

        # Process the user's message using the AI model
        try:
            # If the user starts a new conversation, reset the context
            if user_input.lower() in ["hello", "hi", "hey"]:
                session["context"] = ""  # Clear the context for a fresh start

            response = chain.invoke({"question": user_input, "context": session["context"]})
            print(f"Model response: {response}")  # Debugging statement
        except Exception as e:
            print(f"Error in model invocation: {e}")  # Debugging statement
            return jsonify({"error": str(e)}), 500

        # Update the conversation context for the next interaction
        session["context"] = response  # Store the conversation history in the session

        # Send the response back as JSON
        return jsonify({"response": response})

    return render_template("chat.html")

# Admin Dashboard Route
@app.route("/admin")
def admin():
    if "admin" not in session:
        flash("You need to log in as admin to view this page.", "warning")
        return redirect(url_for("login"))

    users = User.query.all()
    return render_template("admin.html", users=users)

# Admin Delete User Route
@app.route("/admin/delete/<int:user_id>", methods=["POST"])
def delete_user(user_id):
    if "admin" not in session:
        flash("Unauthorized action.", "danger")
        return redirect(url_for("login"))

    user = User.query.get(user_id)
    if user:
        db.session.delete(user)
        db.session.commit()
        flash("User deleted successfully.", "success")

    return redirect(url_for("admin"))

# Function to expand shortcuts
def expand_shortcuts(text):
    # Dictionary of shortcuts and their expanded forms
    shortcuts = {
        "u": "you",
        "r": "are",
        "ur": "your",
        "y": "why",
        "pls": "please",
        "thx": "thanks",
        "btw": "by the way",
        "afaik": "as far as I know",
        "imo": "in my opinion",
        "idk": "I don't know",
        "tbh": "to be honest",
        "omg": "oh my god",
        "lol": "laugh out loud",
        "brb": "be right back",
        "gtg": "got to go",
        "np": "no problem",
        "wbu": "what about you",
        "ikr": "I know, right",
        "smh": "shaking my head",
        "ttyl": "talk to you later",
        "ily": "I love you",
        "idc": "I don't care",
        "rofl": "rolling on the floor laughing",
        "fyi": "for your information",
        "asap": "as soon as possible",
        "atm": "at the moment",
        "b4": "before",
        "b/c": "because",
        "gr8": "great",
        "2day": "today",
        "2moro": "tomorrow",
        "2nite": "tonight",
        "4ever": "forever",
        "4u": "for you",
        "bff": "best friends forever",
        "irl": "in real life",
        "jk": "just kidding",
        "nvm": "never mind",
        "omw": "on my way",
        "tmi": "too much information",
        "wyd": "what are you doing",
        "yw": "you're welcome",
    }

    # Split the input into words and replace shortcuts
    words = text.split()
    expanded_words = [shortcuts.get(word.lower(), word) for word in words]
    return " ".join(expanded_words)

# Initialize the database and migrations (if necessary)
if __name__ == "__main__":
    with app.app_context():
        db.create_all()
    app.run()