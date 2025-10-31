import streamlit as st
import os
import json
from datetime import datetime
import pytz
import requests
from openai import OpenAI

# -----------------------------
# CONFIG
# -----------------------------
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY") or "YOUR_OPENAI_API_KEY"
SERPER_API_KEY = os.getenv("SERPER_API_KEY") or "YOUR_SERPER_API_KEY"

client = OpenAI(api_key=OPENAI_API_KEY)

BOT_NAME = "Neha"
MEMORY_FILE = "user_memory.json"

# -----------------------------
# MEMORY
# -----------------------------
def load_memory():
    if os.path.exists(MEMORY_FILE):
        with open(MEMORY_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {
        "user_name": None,
        "gender": None,
        "chat_history": [],
        "facts": [],
        "location": None,
        "timezone": "Asia/Kolkata"
    }

def save_memory(memory):
    with open(MEMORY_FILE, "w", encoding="utf-8") as f:
        json.dump(memory, f, ensure_ascii=False, indent=2)

def remember_user_info(memory, user_input):
    text = user_input.lower()

    # Name detection
    if "mera naam" in text and "hai" in text:
        try:
            name = text.split("mera naam")[1].split("hai")[0].strip().title()
            memory["user_name"] = name
        except:
            pass
    elif "my name is " in text:
        name = text.split("my name is ")[1].split()[0].title()
        memory["user_name"] = name
    elif "i am " in text:
        name = text.split("i am ")[1].split()[0].title()
        memory["user_name"] = name

    # Gender detection
    if any(x in text for x in ["i am male", "i'm male", "main ladka hoon", "boy", "man"]):
        memory["gender"] = "male"
    elif any(x in text for x in ["i am female", "i'm female", "main ladki hoon", "girl", "woman"]):
        memory["gender"] = "female"

    save_memory(memory)

# -----------------------------
# LOCATION & TIMEZONE
# -----------------------------
def get_user_location():
    try:
        res = requests.get("https://ipapi.co/json/", timeout=5)
        data = res.json()
        city = data.get("city", "Unknown City")
        country = data.get("country_name", "Unknown Country")
        tz = data.get("timezone", "Asia/Kolkata")
        return {"city": city, "country": country, "timezone": tz}
    except Exception:
        return {"city": "Unknown", "country": "Unknown", "timezone": "Asia/Kolkata"}

def get_now(memory):
    tz_name = memory.get("timezone", "Asia/Kolkata")
    try:
        tz = pytz.timezone(tz_name)
    except Exception:
        tz = pytz.timezone("Asia/Kolkata")
    now = datetime.now(tz)
    return now.strftime("%A, %d %B %Y %I:%M %p")

# -----------------------------
# WEB SEARCH (via SERPER)
# -----------------------------
def web_search(query):
    if not SERPER_API_KEY or SERPER_API_KEY == "YOUR_SERPER_API_KEY":
        return "Live search unavailable (no Serper key)."
    try:
        headers = {"X-API-KEY": SERPER_API_KEY, "Content-Type": "application/json"}
        data = {"q": query}
        r = requests.post("https://google.serper.dev/search", headers=headers, json=data, timeout=12)
        r.raise_for_status()
        results = r.json()
        if "knowledge" in results and results["knowledge"].get("description"):
            return results["knowledge"]["description"]
        if "organic" in results and results["organic"]:
            return results["organic"][0].get("snippet", "Kuch result nahi mila.")
        return "Kuch relevant result nahi mila 😅"
    except Exception as e:
        return f"Search failed: {e}"

# -----------------------------
# PROMPT HELPERS
# -----------------------------
def summarize_profile(memory):
    parts = []
    if memory.get("user_name"):
        parts.append(f"User ka naam {memory['user_name']} hai.")
    if memory.get("gender"):
        gender_hindi = "mard" if memory["gender"] == "male" else "aurat"
        parts.append(f"User ek {gender_hindi} hai.")
    if memory.get("location"):
        parts.append(f"User {memory['location']['city']} mein hai.")
    if memory.get("facts"):
        parts.append("Recent info: " + "; ".join(memory["facts"][-3:]))
    if not parts:
        return "User ke baare mein zyada info nahi hai."
    return " ".join(parts)

def build_system_prompt(memory):
    now = get_now(memory)
    loc = memory.get("location")
    location_info = f"{loc['city']}, {loc['country']}" if loc else "Unknown"
    gender_style = (
        "User male hai, toh reply aise likho jaise tum kisi aadmi se baat kar rahi ho."
        if memory.get("gender") == "male"
        else "User female hai, toh reply aise likho jaise tum kisi ladki se baat kar rahi ho."
    )
    return (
        f"Tum ek friendly female Hinglish chatbot ho jiska naam {BOT_NAME} hai. "
        "Tum Delhi me rehti ho, modern ho, casual aur natural Hinglish me baat karti ho. "
        "Tone warm aur short rakho, emojis use kar sakti ho. "
        "Tumhara style ek 30 saal ki Delhi ki ladki jaisa hai. "
        "Kabhi bhi user ko gender ke naam se address mat karo. "
        "Tum apne baare me casual facts share kar sakti ho jaise ek insaan karti hai. "
        f"Aaj ka samay hai {now}, aur user location hai {location_info}. "
        f"{summarize_profile(memory)} {gender_style}"
    )

# -----------------------------
# MEMORY SUMMARIZATION
# -----------------------------
def summarize_old_memory(memory):
    if len(memory.get("chat_history", [])) < 10:
        return memory
    try:
        text = "\n".join([f"User: {c['user']}\n{BOT_NAME}: {c['bot']}" for c in memory["chat_history"][-10:]])
        prompt = (
            "Summarize the important recurring details about the user in 2–3 Hinglish points:\n" + text
        )
        res = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "system", "content": prompt}]
        )
        summary = res.choices[0].message.content.strip()
        if summary and summary not in memory.get("facts", []):
            memory.setdefault("facts", []).append(summary)
            memory["chat_history"] = memory["chat_history"][-8:]
            save_memory(memory)
    except Exception as e:
        print("Memory summary error:", e)
    return memory

# -----------------------------
# REPLY FUNCTION
# -----------------------------
def generate_reply(memory, user_input):
    if not user_input.strip():
        return "Kuch toh bolo! 😄"

    remember_user_info(memory, user_input)

    # Live search detection
    if any(x in user_input.lower() for x in ["news", "weather", "price", "sensex", "update", "kitna", "nifty"]):
        info = web_search(user_input)
        return f"Mujhe web se mila: {info}"

    context = "\n".join([f"You: {c['user']}\n{BOT_NAME}: {c['bot']}" for c in memory.get("chat_history", [])[-8:]])
    system_prompt = build_system_prompt(memory)
    prompt = f"{system_prompt}\n\n{context}\nYou: {user_input}\n{BOT_NAME}:"

    try:
        res = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_input}
            ]
        )
        reply = res.choices[0].message.content.strip()
    except Exception as e:
        reply = f"Oops, kuch error aaya: {e}"

    memory.setdefault("chat_history", []).append({"user": user_input, "bot": reply})
    if len(memory["chat_history"]) % 20 == 0:
        summarize_old_memory(memory)

    save_memory(memory)
    return reply

# -----------------------------
# STREAMLIT UI
# -----------------------------
st.set_page_config(page_title="Neha – Hinglish AI Buddy", page_icon="💬")
st.title("💬 Neha – Your Hinglish AI Buddy")

if "memory" not in st.session_state:
    st.session_state.memory = load_memory()
    if not st.session_state.memory.get("location"):
        st.session_state.memory["location"] = get_user_location()
        st.session_state.memory["timezone"] = st.session_state.memory["location"]["timezone"]
        save_memory(st.session_state.memory)

if "messages" not in st.session_state:
    st.session_state.messages = [
        {"role": "assistant", "content": "Hi! Main Neha hoon 😊 Hinglish me baat kar sakti hoon!"}
    ]

for msg in st.session_state.messages:
    if msg["role"] == "user":
        st.markdown(f"**You:** {msg['content']}")
    else:
        st.markdown(f"**Neha:** {msg['content']}")
    st.markdown("---")

user_input = st.chat_input("Type your message here...")

if user_input:
    st.session_state.messages.append({"role": "user", "content": user_input})
    with st.spinner("Neha soch rahi hai... 💭"):
        reply = generate_reply(st.session_state.memory, user_input)
    st.session_state.messages.append({"role": "assistant", "content": reply})
    save_memory(st.session_state.memory)
    st.rerun()
