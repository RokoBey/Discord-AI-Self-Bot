import requests
import time
import re
import json
from concurrent.futures import ThreadPoolExecutor

TOKEN = 'YOUR_TOKEN_HERE'
API_KEY = 'YOUR_APIKEY_HERE'

TARGET_GUILD_ID = 'DISCORD_SERVER_ID'
API_URL = 'https://api.groq.com/openai/v1/chat/completions'
MODEL = 'llama-3.1-8b-instant'

print("Discord token kontrol ediliyor...")

headers = {'Authorization': TOKEN}
response = requests.get('https://discord.com/api/v9/users/@me', headers=headers)

if response.status_code != 200:
    print(f"❌ Discord token geçersiz! Status: {response.status_code}")
    exit()

user = response.json()
user_id = user['id']
print(f"Discord giriş başarılı: {user['username']}")
print(f"Hesap ID: {user_id}")
print("Bot'u etiketleyerek veya mesajına cevap vererek çağırabilirsin")

processed_messages = {}

executor = ThreadPoolExecutor(max_workers=3)

def send_message(channel_id, content, reply_to=None):
    """Mesaj gönderme fonksiyonu"""
    data = {'content': content}
    if reply_to:
        data['message_reference'] = {'message_id': reply_to}
    
    response = requests.post(
        f'https://discord.com/api/v9/channels/{channel_id}/messages',
        headers=headers,
        json=data
    )
    return response

def get_ai_response(message):
    """AI yanıtını al"""
    try:
        api_headers = {
            'Authorization': f'Bearer {API_KEY}',
            'Content-Type': 'application/json'
        }
        
        api_data = {
            'model': MODEL,
            'messages': [
                {'role': 'system', 'content': 'Kısa ve öz cevap ver. Max 50 kelime. Türkçe cevap ver.'},
                {'role': 'user', 'content': message}
            ],
            'max_tokens': 100,
            'temperature': 0.7,
            'top_p': 0.9,
            'presence_penalty': 0.6,
            'frequency_penalty': 0.6
        }
        
        response = requests.post(
            API_URL,
            headers=api_headers,
            json=api_data,
            timeout=10
        )
        
        if response.status_code == 200:
            result = response.json()
            return result['choices'][0]['message']['content']
        else:
            print(f"❌ Groq API hatası: {response.status_code}")
            return None
            
    except Exception as e:
        print(f"❌ API hatası: {e}")
        return None

def handle_message(channel_id, msg_id, clean_message, author_name, is_mentioned):
    """Mesaj işleme fonksiyonu"""
    # Bu mesajı işlendi olarak işaretle
    processed_messages[msg_id] = True
    
    if not clean_message and is_mentioned:
        send_message(channel_id, "Ne var ne yok? Buyur sorunu sor!", msg_id)
        print(f"{author_name}: (etiket) ✅")
        return
    
    if clean_message:
        print(f"{author_name}: {clean_message}")
        
        cevap = get_ai_response(clean_message)
        
        if cevap:
            send_message(channel_id, cevap, msg_id)
            print(f"Cevap gönderildi: {cevap[:50]}...")
        else:
            send_message(channel_id, "Bir sorun oluştu, tekrar dener misin?", msg_id)

while True:
    try:
        # Kanalları al
        channels_response = requests.get(
            f'https://discord.com/api/v9/guilds/{TARGET_GUILD_ID}/channels',
            headers=headers
        )
        
        if channels_response.status_code != 200:
            print(f"Kanallar alınamadı: {channels_response.status_code}")
            time.sleep(5)
            continue
        
        channels = channels_response.json()
        futures = []
        
        for channel in channels:
            if channel.get('type') != 0:
                continue
            
            channel_id = channel.get('id')
            if not channel_id:
                continue
            
            messages_response = requests.get(
                f'https://discord.com/api/v9/channels/{channel_id}/messages?limit=10',
                headers=headers
            )
            
            if messages_response.status_code != 200:
                continue
            
            messages = messages_response.json()
            
            for msg in messages:
                try:
                    msg_id = msg.get('id')
                    
                    if msg_id in processed_messages:
                        continue
                    
                    content = msg.get('content', '')
                    author = msg.get('author', {})
                    author_id = author.get('id', '')
                    
                    if author_id == user_id:
                        processed_messages[msg_id] = True  # Botun kendi mesajlarını işaretle
                        continue
                    
                    is_mentioned = f'<@{user_id}>' in content or f'<@!{user_id}>' in content
                    
                    is_reply = False
                    if 'referenced_message' in msg and msg['referenced_message']:
                        referenced = msg['referenced_message']
                        if referenced and referenced.get('author', {}).get('id') == user_id:
                            is_reply = True
                    
                    if is_mentioned or is_reply:
                        clean_message = re.sub(f'<@!?{user_id}>', '', content).strip()
                        
                        future = executor.submit(
                            handle_message,
                            channel_id,
                            msg_id,
                            clean_message,
                            author.get('username', 'Bilinmeyen'),
                            is_mentioned
                        )
                        futures.append(future)
                    else:
                        processed_messages[msg_id] = True
                        
                except Exception as e:
                    print(f"❌ Mesaj işleme hatası: {e}")
                    continue
        
        for future in futures:
            try:
                future.result(timeout=1)
            except Exception as e:
                print(f"?: {e}")
        
        if len(processed_messages) > 100:
            # En eski 50 mesajı sil
            keys_to_remove = list(processed_messages.keys())[:50]
            for key in keys_to_remove:
                del processed_messages[key]
        
        time.sleep(1)
        
    except KeyboardInterrupt:
        print("\nBot durduruluyor...")
        executor.shutdown(wait=True)
        break
    except Exception as e:
        print(f"Ana döngü hatası: {e}")
        time.sleep(5)