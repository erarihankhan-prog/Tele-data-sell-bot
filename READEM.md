# Trusted Data Sell Bot - 24/7 Telegram Bot

## Deploy on Render (FREE)

### Step 1: Create GitHub Repository
1. Create a new repository on GitHub
2. Upload all these files to the repository

### Step 2: Deploy on Render
1. Go to [render.com](https://render.com)
2. Sign up with GitHub
3. Click "New +" → "Web Service"
4. Connect your GitHub repository
5. Configure:
   - Name: `trusted-data-sell-bot`
   - Environment: `Python`
   - Region: `Oregon` (or nearest)
   - Branch: `main`
   - Build Command: `pip install -r requirements.txt`
   - Start Command: `python bot2.py`
6. Click "Advanced" and add environment variables:
   - `BOT_TOKEN`: `8654900684:AAE4QjXUsYsqfekp8nQWDXtqGkmHz8Yc_Dg`
   - `ADMIN_ID`: `7998643430`
   - `CHANNEL_USERNAME`: `trusteddatasellupdate`
   - `RENDER`: `true`
7. Click "Create Web Service"

### Step 3: Keep Bot Alive 24/7
Render keeps your bot running 24/7 automatically!

## Deploy on VPS/Linux

```bash
# Install Python and dependencies
sudo apt update
sudo apt install python3.12 python3-pip git -y

# Clone and setup
git clone <your-repo>
cd <your-repo>
pip install -r requirements.txt

# Run the bot
python bot2.py