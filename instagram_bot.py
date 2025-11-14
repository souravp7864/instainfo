import logging
import re
import requests
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from bs4 import BeautifulSoup
import instaloader

# Enable logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

class InstagramBot:
    def __init__(self):
        self.loader = instaloader.Instaloader()
        
    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Send welcome message when command /start is issued."""
        await update.message.reply_text(
            "🤖 Instagram Profile Info Bot\n\n"
            "Send me any Instagram profile link and I'll fetch public information including contact details from bio.\n\n"
            "📋 What I can show:\n"
            "• Profile info (followers, posts, bio)\n"
            "• Contact details from bio (email, phone, social)\n"
            "• Website contact extraction\n\n"
            "Example: https://www.instagram.com/username/\n\n"
            "⚠️ Note: Only works for public profiles with publicly shared contact info"
        )

    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Send help message when command /help is issued."""
        await update.message.reply_text(
            "📖 How to use:\n"
            "1. Send any Instagram profile URL\n"
            "2. I'll extract the public information\n"
            "3. Get details + contact info from bio\n\n"
            "Supported formats:\n"
            "• https://www.instagram.com/username/\n"
            "• https://instagram.com/username\n"
            "• @username\n"
            "• username\n\n"
            "What I extract:\n"
            "• Profile information\n"
            "• Email/phone from bio\n"
            "• Social media handles\n"
            "• Website contacts"
        )

    def extract_username(self, text: str) -> str:
        """Extract username from various Instagram URL formats."""
        text = text.replace('@', '')
        
        patterns = [
            r'instagram\.com/([A-Za-z0-9_.]+)/?',
            r'instagram\.com/([A-Za-z0-9_.]+)\?',
            r'^([A-Za-z0-9_.]+)$'
        ]
        
        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                username = match.group(1)
                username = username.split('/')[0].split('?')[0]
                return username
        return None

    def clean_text(self, text: str) -> str:
        """Clean text to prevent Markdown formatting issues."""
        if not text:
            return ""
        # Remove or escape Markdown special characters
        text = re.sub(r'([*_`\[\]()~>#+=|{}.!-])', r'\\\1', text)
        return text

    def get_profile_info_instaloader(self, username: str) -> dict:
        """Get profile info using instaloader."""
        try:
            profile = instaloader.Profile.from_username(self.loader.context, username)
            
            return {
                'username': profile.username,
                'full_name': self.clean_text(profile.full_name or ''),
                'biography': self.clean_text(profile.biography or ''),
                'followers': profile.followers,
                'following': profile.followees,
                'posts': profile.mediacount,
                'is_private': profile.is_private,
                'is_verified': profile.is_verified,
                'profile_pic_url': profile.profile_pic_url,
                'external_url': profile.external_url,
                'business_category': self.clean_text(profile.business_category_name) if hasattr(profile, 'business_category_name') else None
            }
        except Exception as e:
            logger.error(f"Instaloader error: {e}")
            return None

    def get_profile_info_web(self, username: str) -> dict:
        """Get profile info using web scraping (fallback method)."""
        try:
            url = f"https://www.instagram.com/{username}/"
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
            }
            
            response = requests.get(url, headers=headers, timeout=10)
            soup = BeautifulSoup(response.text, 'html.parser')
            
            scripts = soup.find_all('script')
            for script in scripts:
                if 'window._sharedData' in script.text:
                    data_str = script.text.split('window._sharedData = ')[1].split(';</script>')[0]
                    import json
                    data = json.loads(data_str)
                    
                    try:
                        profile_data = data['entry_data']['ProfilePage'][0]['graphql']['user']
                        return {
                            'username': profile_data.get('username'),
                            'full_name': self.clean_text(profile_data.get('full_name', '')),
                            'biography': self.clean_text(profile_data.get('biography', '')),
                            'followers': profile_data.get('edge_followed_by', {}).get('count'),
                            'following': profile_data.get('edge_follow', {}).get('count'),
                            'posts': profile_data.get('edge_owner_to_timeline_media', {}).get('count'),
                            'is_private': profile_data.get('is_private'),
                            'is_verified': profile_data.get('is_verified'),
                            'profile_pic_url': profile_data.get('profile_pic_url_hd'),
                            'external_url': profile_data.get('external_url')
                        }
                    except (KeyError, IndexError):
                        continue
            return None
        except Exception as e:
            logger.error(f"Web scraping error: {e}")
            return None

    def extract_contact_from_bio(self, bio: str) -> dict:
        """Extract potential contact information from biography."""
        contacts = {
            'emails': [],
            'phones': [],
            'social_handles': []
        }
        
        if not bio:
            return contacts
        
        # Email patterns
        email_pattern = r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'
        email_matches = re.findall(email_pattern, bio, re.IGNORECASE)
        contacts['emails'] = list(set(email_matches))
        
        # Phone patterns
        phone_patterns = [
            r'\b\d{3}[-.]?\d{3}[-.]?\d{4}\b',
            r'\b\(\d{3}\)\s*\d{3}[-.]?\d{4}\b',
            r'\b\d{10}\b',
            r'\b\+\d{1,3}[-.\s]?\(?\d{1,4}\)?[-.\s]?\d{1,4}[-.\s]?\d{1,9}\b'
        ]
        
        for pattern in phone_patterns:
            phone_matches = re.findall(pattern, bio)
            contacts['phones'].extend(phone_matches)
        contacts['phones'] = list(set(contacts['phones']))
        
        # Social media handles
        social_patterns = {
            'telegram': r'telegram[: ]*@([A-Za-z0-9_]+)|tg[: ]*@([A-Za-z0-9_]+)',
            'whatsapp': r'whatsapp[: ]*([0-9+()\- ]+)|wa[: ]*([0-9+()\- ]+)',
            'signal': r'signal[: ]*([0-9+()\- ]+)',
            'snapchat': r'snapchat[: ]*@([A-Za-z0-9_]+)|snap[: ]*@([A-Za-z0-9_]+)',
            'twitter': r'twitter[: ]*@([A-Za-z0-9_]+)|twt[: ]*@([A-Za-z0-9_]+)'
        }
        
        for platform, pattern in social_patterns.items():
            matches = re.findall(pattern, bio, re.IGNORECASE)
            for match in matches:
                # Handle multiple groups in pattern
                for group in match:
                    if group and group.strip():
                        contacts['social_handles'].append(f"{platform.title()}: {group.strip()}")
                        break
        
        # Remove duplicates
        contacts['social_handles'] = list(set(contacts['social_handles']))
        
        return contacts

    def get_contacts_from_website(self, url: str) -> dict:
        """Try to extract contacts from linked website."""
        website_contacts = {
            'emails': [],
            'phones': [],
            'contact_links': []
        }
        
        try:
            if not url.startswith(('http://', 'https://')):
                url = 'https://' + url
            
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            }
            
            response = requests.get(url, headers=headers, timeout=8)
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Extract emails from mailto links
            mailto_links = soup.find_all('a', href=re.compile(r'mailto:'))
            for link in mailto_links:
                email = link['href'].replace('mailto:', '').split('?')[0]
                if email and '@' in email:
                    website_contacts['emails'].append(email)
            
            # Extract emails from text
            email_pattern = r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'
            text_emails = re.findall(email_pattern, soup.get_text())
            website_contacts['emails'].extend(text_emails)
            
            # Extract phones
            tel_links = soup.find_all('a', href=re.compile(r'tel:'))
            for link in tel_links:
                phone = link['href'].replace('tel:', '')
                if phone:
                    website_contacts['phones'].append(phone)
            
            # Remove duplicates
            website_contacts['emails'] = list(set(website_contacts['emails']))[:3]
            website_contacts['phones'] = list(set(website_contacts['phones']))[:3]
            
        except Exception as e:
            logger.error(f"Website contact extraction error: {e}")
        
        return website_contacts

    def format_contact_response(self, contacts: dict, website_contacts: dict) -> str:
        """Format contact information into readable response."""
        response = ""
        
        has_bio_contacts = any(contacts['emails'] or contacts['phones'] or contacts['social_handles'])
        has_website_contacts = any(website_contacts['emails'] or website_contacts['phones'])
        
        if has_bio_contacts:
            response += "📞 Contact Information from Bio:\n"
            
            if contacts['emails']:
                response += "📧 Emails:\n"
                for email in contacts['emails']:
                    response += f"   • {email}\n"
            
            if contacts['phones']:
                response += "📱 Phones:\n"
                for phone in contacts['phones']:
                    response += f"   • {phone}\n"
            
            if contacts['social_handles']:
                response += "💬 Social Handles:\n"
                for handle in contacts['social_handles'][:5]:
                    response += f"   • {handle}\n"
        
        if has_website_contacts:
            if has_bio_contacts:
                response += "\n"
            response += "🌐 Contact Information from Website:\n"
            
            if website_contacts['emails']:
                response += "📧 Website Emails:\n"
                for email in website_contacts['emails']:
                    response += f"   • {email}\n"
            
            if website_contacts['phones']:
                response += "📱 Website Phones:\n"
                for phone in website_contacts['phones']:
                    response += f"   • {phone}\n"
        
        if not has_bio_contacts and not has_website_contacts:
            response = "❌ No contact information found in bio or linked website.\nContact details are only available if the user shares them publicly."
        
        return response

    def format_profile_response(self, profile_info: dict, username: str, contacts: dict, website_contacts: dict) -> str:
        """Format the profile information into a readable response."""
        response = f"📱 Instagram Profile Info\n\n"
        response += f"Username: @{profile_info.get('username', username)}\n"
        
        if profile_info.get('full_name'):
            response += f"👤 Name: {profile_info['full_name']}\n"
        
        if profile_info.get('followers') is not None:
            response += f"👥 Followers: {profile_info['followers']:,}\n"
        
        if profile_info.get('following') is not None:
            response += f"🔄 Following: {profile_info['following']:,}\n"
        
        if profile_info.get('posts') is not None:
            response += f"📸 Posts: {profile_info['posts']:,}\n"
        
        if profile_info.get('biography'):
            bio = profile_info['biography']
            # Truncate very long bios
            if len(bio) > 500:
                bio = bio[:500] + "..."
            response += f"📝 Bio: {bio}\n"
        
        if profile_info.get('external_url'):
            response += f"🔗 Website: {profile_info['external_url']}\n"
        
        if profile_info.get('business_category'):
            response += f"💼 Category: {profile_info['business_category']}\n"
        
        # Status indicators
        status = []
        if profile_info.get('is_private'):
            status.append("🔒 Private")
        else:
            status.append("🔓 Public")
        if profile_info.get('is_verified'):
            status.append("✅ Verified")
        
        if status:
            response += f"\nStatus: {' | '.join(status)}\n"
        
        # Add contact information
        contact_response = self.format_contact_response(contacts, website_contacts)
        if contact_response:
            response += f"\n{contact_response}"
        
        response += f"\n🔗 Profile URL: https://www.instagram.com/{username}/"
        
        return response

    async def handle_instagram_url(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle Instagram profile URLs."""
        user_input = update.message.text.strip()
        username = self.extract_username(user_input)
        
        if not username:
            await update.message.reply_text(
                "❌ Invalid Instagram URL or username.\n"
                "Please send a valid Instagram profile link.\n\n"
                "Examples:\n"
                "• https://www.instagram.com/username/\n"
                "• @username\n"
                "• username"
            )
            return

        # Send typing action
        await update.message.chat.send_action(action="typing")
        
        try:
            # Try instaloader first
            profile_info = self.get_profile_info_instaloader(username)
            
            # If instaloader fails, try web scraping
            if not profile_info:
                await update.message.chat.send_action(action="typing")
                profile_info = self.get_profile_info_web(username)
            
            if profile_info:
                # Check if profile is private
                if profile_info.get('is_private'):
                    await update.message.reply_text(
                        "🔒 This profile is private.\n\n"
                        "I can only access public profile information. "
                        "Please make sure the profile is public or try another account."
                    )
                    return
                
                # Extract contact information
                await update.message.chat.send_action(action="typing")
                bio = profile_info.get('biography', '')
                contacts = self.extract_contact_from_bio(bio)
                
                # Extract website contacts if available
                website_contacts = {'emails': [], 'phones': [], 'contact_links': []}
                if profile_info.get('external_url'):
                    await update.message.chat.send_action(action="typing")
                    website_contacts = self.get_contacts_from_website(profile_info['external_url'])
                
                # Format and send response (without Markdown to avoid parsing errors)
                response = self.format_profile_response(profile_info, username, contacts, website_contacts)
                
                # Split message if too long
                if len(response) > 4000:
                    parts = [response[i:i+4000] for i in range(0, len(response), 4000)]
                    for part in parts:
                        await update.message.reply_text(part)
                else:
                    await update.message.reply_text(response)
                
            else:
                await update.message.reply_text(
                    "❌ Could not fetch profile information.\n\n"
                    "Possible reasons:\n"
                    "• Profile doesn't exist\n"
                    "• Instagram rate limiting\n"
                    "• Network issues\n"
                    "• Profile is private\n\n"
                    "Please try again later or check the username."
                )
                
        except Exception as e:
            logger.error(f"Error processing request: {e}")
            await update.message.reply_text(
                "❌ An error occurred while fetching profile information.\n"
                "Please try again later."
            )

def main():
    """Start the bot."""
    # Replace with your bot token from BotFather
    TOKEN = "8507471476:AAHkLlfP4uZ8DwNsoffhDPQsfh61QoX9aZc"
    
    # Create bot instance
    insta_bot = InstagramBot()
    
    # Create application
    application = Application.builder().token(TOKEN).build()

    # Add handlers
    application.add_handler(CommandHandler("start", insta_bot.start))
    application.add_handler(CommandHandler("help", insta_bot.help_command))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, insta_bot.handle_instagram_url))

    # Start the Bot
    print("🤖 Bot is running...")
    print("Send /start to your bot on Telegram to begin")
    application.run_polling()

if __name__ == '__main__':
    main()