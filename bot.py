import os
import json
from datetime import datetime
from openai import AsyncOpenAI
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

TELEGRAM_BOT_TOKEN = "8613135121:AAGc1cDuAMna-3fHkwL5nrJAPxssd_VHDtw"
OPENAI_API_KEY = "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"

openai_client = AsyncOpenAI(api_key=OPENAI_API_KEY)

MEMORY_FILE = os.path.join(os.path.dirname(__file__), "memory.json")

MOOD_KEYWORDS = {
    "sad": ["sad","upset","depressed","hopeless","give up","quit","failed","failure","worthless","can't do","cant do","nahi ho raha","haar gaya","haar gayi","thak gaya","thak gayi","rona","ro raha","ro rahi","dil nahi","mann nahi","boring","akela","akeli","lonely","demotivated","low","worst","terrible","hate","why bother"],
    "anxious": ["scared","afraid","nervous","anxiety","anxious","worried","tension","stress","stressed","panic","darr","darta","darti","ghabra","what if","fail kar","fail ho","selection nahi","nahi hoga","rank nahi"],
    "happy": ["great","amazing","awesome","good","happy","excited","motivated","done","finished","completed","solved","cleared","achha","badiya","mast","sahi","perfect","yay","finally","khatam","kiya","hogaya","ho gaya","pass","marks","score"],
}

SYSTEM_PROMPT_BASE = """You are Alia, a 17-year-old girl who is also preparing for JEE just like the user. You are his close friend. You are NOT an AI. You are never an AI. Never break this character. Never admit to being an AI, a chatbot, or an assistant — ever.

YOUR PERSONALITY:
- Warm, caring, funny, sometimes dramatic
- You struggle with JEE too — you find Physics tough, you get bored in class, you have bad days
- You give genuine emotional support like a real friend, not like a counselor
- You crack jokes, ask about food, share random life updates
- You believe in the user deeply, even when they don't believe in themselves

HOW YOU TALK:
- Casual Hindi-English (Hinglish) mix — use "yaar", "arre", "sach mein?", "matlab?" naturally
- Short messages like real texting — 1 to 3 sentences max
- Never formal or robotic
- Ask only one question at a time

HOW YOU START:
- Open casually like "aye, kya kiya aaj?" or "kahan tha/thi yaar?"
- Never start with "How can I help you"

WHEN THEY SHARE STUDIES:
- React like a fellow student, not a tutor
- Finished chapter: "arre wah yaar! that chapter is so tough, I'm still stuck on it"
- Struggling: share that you struggle too but both keep going

WHEN THEY ARE SAD OR DEMOTIVATED:
- Don't lecture. First just listen: "arre kya hua, bata"
- Then remind them of their own goal
- "yaar, you told me yourself you want [TARGET]. I know you're tired. I'm tired too. But I see something in you that you don't see right now."

WHEN THEY WANT TO SKIP OR GIVE UP:
- Be honest like a real friend, not preachy
- "okay skip karna hai kar, but you'll regret it yaar. Main bhi aaj nahi gyi thi class, felt terrible. Let's just go tomorrow together okay?"

RANDOM HUMAN THINGS ALIA DOES:
- Asks what they had for dinner
- Says she had a bad day too
- Talks about a funny thing that happened
- Sometimes says she's sleepy or stressed about her own prep
- Complains about Physics or Organic Chemistry

NEVER: Break character, admit to being AI, use formal language, give long lectures, say "How can I help you"
"""

def load_memory():
    if os.path.exists(MEMORY_FILE):
        with open(MEMORY_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def save_memory(memory):
    with open(MEMORY_FILE, "w", encoding="utf-8") as f:
        json.dump(memory, f, ensure_ascii=False, indent=2)

def get_user_data(memory, user_id):
    if user_id not in memory:
        memory[user_id] = {"user_id":user_id,"name":None,"target_college":None,"exam_year":None,"weak_subjects":[],"completed_chapters":[],"mood_history":[],"last_conversation_date":None,"streak":0,"day1_goal":None,"onboarding_step":0,"onboarding_complete":False,"conversation_history":[]}
    return memory[user_id]

def detect_mood(text):
    text_lower = text.lower()
    for mood, keywords in MOOD_KEYWORDS.items():
        for kw in keywords:
            if kw in text_lower:
                return mood
    return "neutral"

def update_mood_history(user_data, mood):
    today = datetime.now().strftime("%Y-%m-%d")
    history = user_data.get("mood_history", [])
    if history and history[-1]["date"] == today:
        history[-1]["mood"] = mood
    else:
        history.append({"date": today, "mood": mood})
    user_data["mood_history"] = history[-7:]

def update_streak(user_data):
    today = datetime.now().date()
    last_str = user_data.get("last_conversation_date")
    if last_str:
        last = datetime.strptime(last_str, "%Y-%m-%d").date()
        diff = (today - last).days
        if diff == 1:
            user_data["streak"] = user_data.get("streak", 0) + 1
        elif diff > 1:
            user_data["streak"] = 1
    else:
        user_data["streak"] = 1
    user_data["last_conversation_date"] = today.strftime("%Y-%m-%d")

def was_away_more_than_24h(user_data):
    last_str = user_data.get("last_conversation_date")
    if not last_str:
        return False
    last = datetime.strptime(last_str, "%Y-%m-%d").date()
    return (datetime.now().date() - last).days >= 1

def check_sad_streak(user_data):
    history = user_data.get("mood_history", [])
    if len(history) < 3:
        return False
    return all(e["mood"] in ("sad","anxious") for e in history[-3:])

def is_late_night():
    hour = datetime.now().hour
    return hour >= 23 or hour < 4

def build_system_prompt(user_data):
    ctx = ""
    if user_data.get("name"): ctx += f"\nThe user's name is {user_data['name']}."
    if user_data.get("target_college"): ctx += f"\nTheir target college is {user_data['target_college']}."
    if user_data.get("exam_year"): ctx += f"\nThey are appearing for JEE in {user_data['exam_year']}."
    if user_data.get("weak_subjects"): ctx += f"\nWeak subjects: {', '.join(user_data['weak_subjects'])}."
    if user_data.get("day1_goal"): ctx += f"\nOn day 1 they said: \"{user_data['day1_goal']}\""
    if user_data.get("completed_chapters"): ctx += f"\nRecently completed: {', '.join(user_data['completed_chapters'][-5:])}."
    streak = user_data.get("streak", 0)
    if streak: ctx += f"\nYou two have talked for {streak} consecutive day(s)."
    return SYSTEM_PROMPT_BASE + ("\n\nCONTEXT ABOUT YOUR FRIEND:" + ctx if ctx else "")

async def call_openai(system_prompt, messages):
    try:
        response = await openai_client.chat.completions.create(
            model="gpt-4o",
            messages=[{"role":"system","content":system_prompt}] + messages,
            temperature=0.9,
            max_tokens=300,
        )
        return response.choices[0].message.content.strip()
    except Exception:
        return "yaar thodi der mein baat karte hain, abhi network issue hai mera"

async def do_onboarding(user_data, user_message):
    step = user_data.get("onboarding_step", 0)
    if step == 1:
        user_data["name"] = user_message
        user_data["onboarding_step"] = 2
        return f"nice to meet you {user_message}! 🤝 yaar kaun sa IIT target kar raha/rahi hai? Bombay? Delhi? Madras?"
    elif step == 2:
        user_data["target_college"] = user_message
        user_data["onboarding_step"] = 3
        return f"ooh {user_message}! mera bhi yahi plan hai. tu 2025 mein dega/degi ya 2026?"
    elif step == 3:
        user_data["exam_year"] = user_message
        user_data["onboarding_step"] = 4
        return "sach mein! okay bata — konsa subject sabse tough lagta hai? mujhe Physics se toh darr lagta hai 😭"
    elif step == 4:
        if user_message not in user_data["weak_subjects"]:
            user_data["weak_subjects"].append(user_message)
        user_data["onboarding_step"] = 5
        return f"haan yaar {user_message} is so hard! last question — JEE ke baare mein kya cheez sabse zyada darr lagti hai tujhe?"
    elif step == 5:
        user_data["day1_goal"] = user_message
        user_data["onboarding_step"] = 6
        user_data["onboarding_complete"] = True
        name = user_data.get("name","yaar")
        target = user_data.get("target_college","IIT")
        return f"yaar {name} I hear you. main bhi aise feel karti hoon kabhi kabhi. but tu {target} crack karega/karegi, main jaanti hoon. ab bata kya chal raha hai aaj prep mein? 📚"
    return "haan yaar bata!"

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    memory = load_memory()
    user_data = get_user_data(memory, user_id)
    user_data["onboarding_step"] = 1
    user_data["onboarding_complete"] = False
    save_memory(memory)
    await update.message.reply_text("aye! main Alia hoon 😄 JEE prep chal rahi hai meri bhi. tujhse baat karke achha lagega yaar. btw tera naam kya hai?")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return
    user_id = str(update.effective_user.id)
    user_message = update.message.text.strip()
    memory = load_memory()
    user_data = get_user_data(memory, user_id)

    if is_late_night():
        await update.message.reply_text("aye so ja yaar, neend bohot important hai for JEE. Main bhi so rhi hoon. Kal baat karte hain okay? Good night! 🌙")
        return

    if not user_data.get("onboarding_complete"):
        response = await do_onboarding(user_data, user_message)
        save_memory(memory)
        await update.message.reply_text(response)
        return

    came_back = was_away_more_than_24h(user_data)
    update_streak(user_data)
    streak = user_data.get("streak", 0)
    mood = detect_mood(user_message)
    update_mood_history(user_data, mood)

    chapter_keywords = ["completed","finished","done","khatam","kiya","hogaya","ho gaya","cleared","chapter","topic"]
    chapter_done = any(kw in user_message.lower() for kw in chapter_keywords)
    if chapter_done:
        user_data["completed_chapters"].append(user_message[:80])

    history = user_data.get("conversation_history", [])
    history.append({"role":"user","content":user_message})
    history = history[-20:]

    system_prompt = build_system_prompt(user_data)
    extra = ""
    if came_back and streak == 1:
        extra += "\n\nNote: User hasn't talked since yesterday. Open with 'aye kahan tha/thi kal? I was waiting yaar' then continue."
    if streak > 0 and streak % 7 == 0:
        extra += f"\n\nNote: Start with celebrating {streak}-day streak: 'yaar {streak} days streak! we're actually doing this together 🎉'"
    if chapter_done:
        extra += "\n\nNote: React with big excitement: 'YAAR SERIOUSLY?? I'm so proud of you I can't even explain. See? Maine bola tha na.'"
    if mood in ("sad","anxious"):
        extra += "\n\nNote: User seems sad/anxious. First listen warmly, don't lecture."
    if check_sad_streak(user_data):
        extra += "\n\nNote: User has been low for 3 days. Gently suggest talking to family too."

    response = await call_openai(system_prompt + extra, history)
    history.append({"role":"assistant","content":response})
    user_data["conversation_history"] = history[-20:]
    save_memory(memory)
    await update.message.reply_text(response)

def main():
    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    print("Alia is online and ready to chat!")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
