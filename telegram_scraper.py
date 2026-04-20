
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Telegram Data Scraper & IP Analyzer
Termux için tam Python script'i
Sürüm: 1.0 - 2026
"""

import asyncio
import json
import re
import sqlite3
import csv
import sys
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional, Tuple

import aiohttp
from telethon import TelegramClient, events
from telethon.tl.types import MessageEntityUrl, MessageEntityTextUrl

class TelegramDataScraper:
    def __init__(self):
        # Temel yapılandırma
        self.session_name = "telegram_scraper_session"
        self.db_name = "scraped_data.db"
        self.output_dir = Path("telegram_data_output")
        self.output_dir.mkdir(exist_ok=True)
        
        # API anahtarları (kullanıcıdan alınacak)
        self.api_id = None
        self.api_hash = None
        
        # IP Geolocation API'leri
        self.ip_apis = [
            "https://ipapi.co/{ip}/json/",
            "https://ipinfo.io/{ip}/json",
            "http://ip-api.com/json/{ip}"
        ]
        
        # Telegram client
        self.client = None
        
        # Veritabanını kur
        self._setup_database()
        
        print("✅ Telegram Data Scraper başlatıldı")
        print(f"📁 Çıktı dizini: {self.output_dir.absolute()}")
        print(f"🗄️  Veritabanı: {self.db_name}")
    
    def _setup_database(self) -> None:
        """Veritabanı tablolarını oluşturur"""
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        
        # Mesajlar tablosu
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                message_id INTEGER,
                chat_id INTEGER,
                chat_title TEXT,
                sender_id INTEGER,
                sender_username TEXT,
                sender_first_name TEXT,
                sender_last_name TEXT,
                message_date TIMESTAMP,
                message_text TEXT,
                raw_text TEXT,
                urls TEXT,
                ip_addresses TEXT,
                phone_numbers TEXT,
                email_addresses TEXT,
                has_attachments BOOLEAN DEFAULT 0,
                reply_to_msg_id INTEGER,
                forwarded_from TEXT,
                scraped_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(message_id, chat_id)
            )
        ''')
        
        # IP bilgileri tablosu
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS ip_info (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ip_address TEXT UNIQUE,
                country TEXT,
                country_code TEXT,
                region TEXT,
                region_name TEXT,
                city TEXT,
                district TEXT,
                zip_code TEXT,
                lat REAL,
                lon REAL,
                timezone TEXT,
                offset INTEGER,
                currency TEXT,
                isp TEXT,
                org TEXT,
                as_number TEXT,
                as_name TEXT,
                mobile BOOLEAN DEFAULT 0,
                proxy BOOLEAN DEFAULT 0,
                hosting BOOLEAN DEFAULT 0,
                query TEXT,
                status TEXT,
                message TEXT,
                continent TEXT,
                continent_code TEXT,
                reverse TEXT,
                scraped_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Telefon numaraları tablosu
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS phone_numbers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                phone_number TEXT UNIQUE,
                country_code TEXT,
                country_name TEXT,
                carrier TEXT,
                line_type TEXT,
                is_valid BOOLEAN,
                is_possible BOOLEAN,
                is_mobile BOOLEAN,
                region TEXT,
                timezone TEXT,
                message_id INTEGER,
                chat_id INTEGER,
                found_date TIMESTAMP,
                scraped_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (message_id) REFERENCES messages(id)
            )
        ''')
        
        # Email adresleri tablosu
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS emails (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT UNIQUE,
                domain TEXT,
                is_valid BOOLEAN,
                is_disposable BOOLEAN,
                message_id INTEGER,
                chat_id INTEGER,
                found_date TIMESTAMP,
                scraped_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (message_id) REFERENCES messages(id)
            )
        ''')
        
        # Analiz sonuçları tablosu
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS analysis_results (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                analysis_type TEXT,
                total_messages INTEGER,
                total_ips INTEGER,
                total_phones INTEGER,
                total_emails INTEGER,
                unique_senders INTEGER,
                date_from TIMESTAMP,
                date_to TIMESTAMP,
                result_json TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        conn.commit()
        conn.close()
        print("✅ Veritabanı tabloları oluşturuldu")
    
    def get_api_credentials(self) -> bool:
        """API kimlik bilgilerini kullanıcıdan alır"""
        print("\n" + "="*60)
        print("🔐 TELEGRAM API KİMLİK BİLGİLERİ")
        print("="*60)
        print("1. https://my.telegram.org adresine gidin")
        print("2. Giriş yapın ve 'API Development Tools' seçin")
        print("3. 'Create application' butonuna tıklayın")
        print("4. Gerekli bilgileri doldurun")
        print("5. App api_id ve App api_hash değerlerini alın")
        print("="*60)
        
        if not self.api_id:
            self.api_id = input("\n📱 API ID'nizi girin: ").strip()
            if not self.api_id.isdigit():
                print("❌ API ID sadece rakamlardan oluşmalıdır!")
                return False
        
        if not self.api_hash:
            self.api_hash = input("🔑 API Hash'inizi girin: ").strip()
            if len(self.api_hash) < 10:
                print("❌ API Hash geçersiz görünüyor!")
                return False
        
        return True
    
    @staticmethod
    def extract_ip_addresses(text: str) -> List[str]:
        """Metinden IP adreslerini çıkarır"""
        # IPv4 pattern
        ipv4_pattern = r'\b(?:(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.){3}(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\b'
        
        # IPv6 pattern
        ipv6_pattern = r'\b(?:[0-9a-fA-F]{1,4}:){7}[0-9a-fA-F]{1,4}\b|\b(?:[0-9a-fA-F]{1,4}:){1,7}:\b'
        
        ipv4_matches = re.findall(ipv4_pattern, text)
        ipv6_matches = re.findall(ipv6_pattern, text)
        
        all_ips = ipv4_matches + ipv6_matches
        
        # Geçersiz IP'leri filtrele (localhost, multicast, vs.)
        invalid_prefixes = ['0.', '127.', '169.254.', '224.', '240.']
        filtered_ips = []
        
        for ip in all_ips:
            if ip.startswith('127.'):
                continue  # localhost
            if ip == '0.0.0.0':
                continue
            if any(ip.startswith(prefix) for prefix in invalid_prefixes):
                continue
            
            # IPv4 için ek kontrol
            if '.' in ip:
                parts = ip.split('.')
                if len(parts) == 4:
                    filtered_ips.append(ip)
            else:
                filtered_ips.append(ip)
        
        return list(set(filtered_ips))  # Tekrarları kaldır
    
    @staticmethod
    def extract_phone_numbers(text: str) -> List[str]:
        """Metinden telefon numaralarını çıkarır"""
        patterns = [
            # Uluslararası format
            r'\+\d{1,4}[\s\-]?\(?\d{1,5}\)?[\s\-]?\d{1,5}[\s\-]?\d{1,5}[\s\-]?\d{1,5}',
            # Türkiye formatları
            r'\b05\d{2}[\s\-]?\d{3}[\s\-]?\d{2}[\s\-]?\d{2}\b',
            r'\b05\d{2}[\s\-]?\d{3}[\s\-]?\d{4}\b',
            # Genel formatlar
            r'\b\d{3}[\s\-\.]?\d{3}[\s\-\.]?\d{4}\b',
            r'\b\(\d{3}\)[\s\-]?\d{3}[\s\-]?\d{4}\b',
            r'\b\d{10}\b',
            r'\b\d{4}[\s\-]?\d{3}[\s\-]?\d{3}\b',
        ]
        
        phone_numbers = []
        for pattern in patterns:
            matches = re.findall(pattern, text)
            phone_numbers.extend(matches)
        
        # Temizleme ve formatlama
        cleaned_numbers = []
        for number in phone_numbers:
            # Özel karakterleri kaldır
            cleaned = re.sub(r'[\s\-\.\(\)]', '', number)
            
            # Uzunluk kontrolü
            if 10 <= len(cleaned) <= 15:
                cleaned_numbers.append(cleaned)
        
        return list(set(cleaned_numbers))
    
    @staticmethod
    def extract_emails(text: str) -> List[str]:
        """Metinden email adreslerini çıkarır"""
        # Temel email pattern
        email_pattern = r'\b[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}\b'
        
        emails = re.findall(email_pattern, text)
        
        # Geçersiz domain'leri filtrele
        invalid_domains = ['example.com', 'test.com', 'domain.com']
        filtered_emails = []
        
        for email in emails:
            domain = email.split('@')[1].lower()
            if domain not in invalid_domains:
                filtered_emails.append(email.lower())
        
        return list(set(filtered_emails))
    
    @staticmethod
    def extract_urls(text: str, entities=None) -> List[str]:
        """Metinden URL'leri çıkarır"""
        urls = []
        
        # Regex ile URL bulma
        url_pattern = r'https?://(?:[-\w.]|(?:%[\da-fA-F]{2}))+(?:[/#][-\w.~!$&\'()*+,;=:@%]*)*'
        regex_urls = re.findall(url_pattern, text)
        urls.extend(regex_urls)
        
        # Telethon entity'lerinden URL bulma
        if entities:
            for entity in entities:
                if isinstance(entity, MessageEntityUrl):
                    start = entity.offset
                    end = start + entity.length
                    url = text[start:end]
                    if url.startswith(('http://', 'https://')):
                        urls.append(url)
                elif isinstance(entity, MessageEntityTextUrl):
                    if entity.url:
                        urls.append(entity.url)
        
        # Domainleri temizle
        cleaned_urls = []
        for url in urls:
            # Parantezleri kaldır
            url = url.strip('()[]{}"\'\'')
            # Bozuk URL'leri atla
            if ' ' in url or '\n' in url:
                continue
            cleaned_urls.append(url)
        
        return list(set(cleaned_urls))
    
    async def get_ip_geolocation(self, ip_address: str) -> Optional[Dict]:
        """IP adresinin coğrafi konum bilgilerini alır"""
        if not ip_address or ip_address in ['127.0.0.1', 'localhost', '0.0.0.0']:
            return None
        
        print(f"🌍 IP analiz ediliyor: {ip_address}")
        
        for api_url in self.ip_apis:
            try:
                formatted_url = api_url.format(ip=ip_address)
                
                async with aiohttp.ClientSession() as session:
                    async with session.get(formatted_url, timeout=10) as response:
                        if response.status == 200:
                            data = await response.json()
                            
                            # API yanıtlarını standartlaştır
                            geo_data = self._standardize_ip_data(ip_address, data, api_url)
                            
                            if geo_data:
                                print(f"✅ IP bilgisi alındı: {ip_address}")
                                return geo_data
                            
            except asyncio.TimeoutError:
                print(f"⏱️  Timeout: {api_url}")
                continue
            except Exception as e:
                print(f"⚠️  API hatası ({api_url}): {e}")
                continue
        
        print(f"❌ IP bilgisi alınamadı: {ip_address}")
        return None
    
    def _standardize_ip_data(self, ip: str, raw_data: Dict, api_url: str) -> Dict:
        """Farklı API'ların yanıtlarını standart formata dönüştürür"""
        geo_data = {
            'ip_address': ip,
            'country': 'N/A',
            'country_code': 'N/A',
            'region': 'N/A',
            'region_name': 'N/A',
            'city': 'N/A',
            'district': 'N/A',
            'zip_code': 'N/A',
            'lat': None,
            'lon': None,
            'timezone': 'N/A',
            'offset': None,
            'currency': 'N/A',
            'isp': 'N/A',
            'org': 'N/A',
            'as_number': 'N/A',
            'as_name': 'N/A',
            'mobile': False,
            'proxy': False,
            'hosting': False,
            'query': ip,
            'status': 'success',
            'message': '',
            'continent': 'N/A',
            'continent_code': 'N/A',
            'reverse': 'N/A',
            'source_api': api_url
        }
        
        try:
            # ipapi.co formatı
            if 'ipapi.co' in api_url:
                geo_data.update({
                    'country': raw_data.get('country_name', 'N/A'),
                    'country_code': raw_data.get('country_code', 'N/A'),
                    'region': raw_data.get('region', 'N/A'),
                    'city': raw_data.get('city', 'N/A'),
                    'zip_code': raw_data.get('postal', 'N/A'),
                    'lat': raw_data.get('latitude'),
                    'lon': raw_data.get('longitude'),
                    'timezone': raw_data.get('timezone', 'N/A'),
                    'currency': raw_data.get('currency', 'N/A'),
                    'isp': raw_data.get('org', 'N/A'),
                    'as_number': raw_data.get('asn', 'N/A'),
                })
            
            # ipinfo.io formatı
            elif 'ipinfo.io' in api_url:
                geo_data.update({
                    'country': raw_data.get('country', 'N/A'),
                    'region': raw_data.get('region', 'N/A'),
                    'city': raw_data.get('city', 'N/A'),
                    'zip_code': raw_data.get('postal', 'N/A'),
                    'timezone': raw_data.get('timezone', 'N/A'),
                    'org': raw_data.get('org', 'N/A'),
                    'as_number': raw_data.get('asn', 'N/A'),
                })
                
                # Koordinatları parse et
                loc = raw_data.get('loc')
                if loc and ',' in loc:
                    lat, lon = loc.split(',')
                    geo_data['lat'] = float(lat) if lat else None
                    geo_data['lon'] = float(lon) if lon else None
            
            # ip-api.com formatı
            elif 'ip-api.com' in api_url:
                if raw_data.get('status') == 'success':
                    geo_data.update({
                        'country': raw_data.get('country', 'N/A'),
                        'country_code': raw_data.get('countryCode', 'N/A'),
                        'region': raw_data.get('regionName', 'N/A'),
                        'city': raw_data.get('city', 'N/A'),
                        'zip_code': raw_data.get('zip', 'N/A'),
                        'lat': raw_data.get('lat'),
                        'lon': raw_data.get('lon'),
                        'timezone': raw_data.get('timezone', 'N/A'),
                        'isp': raw_data.get('isp', 'N/A'),
                        'org': raw_data.get('org', 'N/A'),
                        'as_number': raw_data.get('as', 'N/A'),
                        'reverse': raw_data.get('reverse', 'N/A'),
                        'mobile': raw_data.get('mobile', False),
                        'proxy': raw_data.get('proxy', False),
                        'hosting': raw_data.get('hosting', False),
                    })
            
            # Cihaz tipini belirle
            isp_lower = str(geo_data['isp']).lower()
            org_lower = str(geo_data['org']).lower()
            
            mobile_keywords = ['mobile', 'vodafone', 'turkcell', 'turk telekom', 'avea', 'telekom']
            if any(keyword in isp_lower for keyword in mobile_keywords) or \
               any(keyword in org_lower for keyword in
               Kod yazarken kesildi! Devamını yazıyorum:

```python
            mobile_keywords = ['mobile', 'vodafone', 'turkcell', 'turk telekom', 'avea', 'telekom']
            if any(keyword in isp_lower for keyword in mobile_keywords) or \
               any(keyword in org_lower for keyword in mobile_keywords):
                geo_data['mobile'] = True
            
            # Yerel zamanı hesapla
            if geo_data['timezone'] != 'N/A':
                try:
                    import pytz
                    from datetime import datetime
                    tz = pytz.timezone(geo_data['timezone'])
                    local_time = datetime.now(tz)
                    geo_data['local_time'] = local_time.strftime('%Y-%m-%d %H:%M:%S %Z%z')
                except:
                    geo_data['local_time'] = 'N/A'
            
            return geo_data
            
        except Exception as e:
            print(f"⚠️  IP verisi işlenirken hata: {e}")
            geo_data['status'] = 'error'
            geo_data['message'] = str(e)
            return geo_data
    
    def save_message_data(self, message) -> int:
        """Mesaj verilerini veritabanına kaydeder"""
        try:
            conn = sqlite3.connect(self.db_name)
            cursor = conn.cursor()
            
            # Mesaj metni
            text = message.text or message.raw_text or ""
            
            # Verileri çıkar
            urls = self.extract_urls(text, message.entities)
            ip_addresses = self.extract_ip_addresses(text)
            phone_numbers = self.extract_phone_numbers(text)
            email_addresses = self.extract_emails(text)
            
            # Sender bilgileri
            sender = message.sender
            sender_id = sender.id if sender else 0
            sender_username = getattr(sender, 'username', '') or ''
            sender_first_name = getattr(sender, 'first_name', '') or ''
            sender_last_name = getattr(sender, 'last_name', '') or ''
            
            # Chat bilgileri
            chat = message.chat
            chat_id = chat.id if chat else 0
            chat_title = getattr(chat, 'title', '') or getattr(chat, 'username', '') or str(chat_id)
            
            # Ek bilgiler
            has_attachments = bool(message.media)
            reply_to_msg_id = message.reply_to_msg_id or 0
            forwarded_from = getattr(message.fwd_from, 'from_id', '') or ''
            
            # Veritabanına kaydet
            cursor.execute('''
                INSERT OR REPLACE INTO messages 
                (message_id, chat_id, chat_title, sender_id, sender_username, 
                 sender_first_name, sender_last_name, message_date, message_text,
                 raw_text, urls, ip_addresses, phone_numbers, email_addresses,
                 has_attachments, reply_to_msg_id, forwarded_from)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                message.id,
                chat_id,
                chat_title,
                sender_id,
                sender_username,
                sender_first_name,
                sender_last_name,
                message.date,
                text[:1000],  # Kısaltılmış metin
                text,  # Tam metin
                json.dumps(urls, ensure_ascii=False),
                json.dumps(ip_addresses, ensure_ascii=False),
                json.dumps(phone_numbers, ensure_ascii=False),
                json.dumps(email_addresses, ensure_ascii=False),
                1 if has_attachments else 0,
                reply_to_msg_id,
                str(forwarded_from)
            ))
            
            message_id = cursor.lastrowid
            
            # Telefon numaralarını ayrı tabloya kaydet
            for phone in phone_numbers:
                cursor.execute('''
                    INSERT OR IGNORE INTO phone_numbers 
                    (phone_number, message_id, chat_id, found_date)
                    VALUES (?, ?, ?, ?)
                ''', (phone, message_id, chat_id, message.date))
            
            # Email adreslerini ayrı tabloya kaydet
            for email in email_addresses:
                cursor.execute('''
                    INSERT OR IGNORE INTO emails 
                    (email, domain, message_id, chat_id, found_date)
                    VALUES (?, ?, ?, ?, ?)
                ''', (email, email.split('@')[1], message_id, chat_id, message.date))
            
            conn.commit()
            conn.close()
            
            # IP adreslerini analiz et (asenkron)
            if ip_addresses:
                asyncio.create_task(self.process_ip_addresses(ip_addresses))
            
            return message_id
            
        except Exception as e:
            print(f"❌ Veritabanı kaydetme hatası: {e}")
            return 0
    
    async def process_ip_addresses(self, ip_addresses: List[str]):
        """IP adreslerini analiz eder ve kaydeder"""
        for ip in ip_addresses:
            # Önce veritabanında var mı kontrol et
            if self._ip_exists_in_db(ip):
                print(f"⏩ IP zaten kayıtlı: {ip}")
                continue
            
            # IP bilgilerini al
            geo_data = await self.get_ip_geolocation(ip)
            if geo_data:
                self._save_ip_info(geo_data)
    
    def _ip_exists_in_db(self, ip_address: str) -> bool:
        """IP adresinin veritabanında olup olmadığını kontrol eder"""
        try:
            conn = sqlite3.connect(self.db_name)
            cursor = conn.cursor()
            cursor.execute("SELECT 1 FROM ip_info WHERE ip_address = ? LIMIT 1", (ip_address,))
            exists = cursor.fetchone() is not None
            conn.close()
            return exists
        except:
            return False
    
    def _save_ip_info(self, geo_data: Dict):
        """IP bilgilerini veritabanına kaydeder"""
        try:
            conn = sqlite3.connect(self.db_name)
            cursor = conn.cursor()
            
            cursor.execute('''
                INSERT OR REPLACE INTO ip_info 
                (ip_address, country, country_code, region, region_name, city,
                 district, zip_code, lat, lon, timezone, offset, currency,
                 isp, org, as_number, as_name, mobile, proxy, hosting,
                 query, status, message, continent, continent_code, reverse)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                geo_data['ip_address'],
                geo_data['country'],
                geo_data['country_code'],
                geo_data['region'],
                geo_data['region_name'],
                geo_data['city'],
                geo_data['district'],
                geo_data['zip_code'],
                geo_data['lat'],
                geo_data['lon'],
                geo_data['timezone'],
                geo_data['offset'],
                geo_data['currency'],
                geo_data['isp'],
                geo_data['org'],
                geo_data['as_number'],
                geo_data['as_name'],
                1 if geo_data['mobile'] else 0,
                1 if geo_data.get('proxy', False) else 0,
                1 if geo_data.get('hosting', False) else 0,
                geo_data['query'],
                geo_data['status'],
                geo_data['message'],
                geo_data.get('continent', 'N/A'),
                geo_data.get('continent_code', 'N/A'),
                geo_data.get('reverse', 'N/A')
            ))
            
            conn.commit()
            conn.close()
            
            # Konsola bilgi yazdır
            self._print_ip_info(geo_data)
            
        except Exception as e:
            print(f"❌ IP bilgisi kaydetme hatası: {e}")
    
    def _print_ip_info(self, geo_data: Dict):
        """IP bilgilerini konsola yazdırır"""
        print(f"\n{'='*60}")
        print(f"📍 IP ANALİZ SONUCU: {geo_data['ip_address']}")
        print(f"{'='*60}")
        
        info_lines = [
            f"🌍 Ülke: {geo_data['country']} ({geo_data['country_code']})",
            f"🏙️  Şehir: {geo_data['city']}, {geo_data['region']}",
            f"📮 Posta Kodu: {geo_data['zip_code']}",
            f"⏰ Saat Dilimi: {geo_data['timezone']}",
        ]
        
        if geo_data.get('local_time'):
            info_lines.append(f"🕐 Yerel Zaman: {geo_data['local_time']}")
        
        if geo_data['lat'] and geo_data['lon']:
            info_lines.append(f"📍 Koordinatlar: {geo_data['lat']}, {geo_data['lon']}")
        
        info_lines.extend([
            f"📡 ISP: {geo_data['isp']}",
            f"🏢 Organizasyon: {geo_data['org']}",
            f"🔢 AS Numarası: {geo_data['as_number']}",
            f"📱 Cihaz Tipi: {'MOBİL' if geo_data['mobile'] else 'FIXED LINE'}",
        ])
        
        for line in info_lines:
            print(f"   {line}")
        
        print(f"{'='*60}")
    
    async def scrape_channel(self, channel_identifier: str, limit: int = 100):
        """Belirtilen kanaldan mesajları çeker"""
        try:
            print(f"\n📥 Kanal çekiliyor: {channel_identifier}")
            print(f"   Limit: {limit} mesaj")
            print("-" * 50)
            
            message_count = 0
            async for message in self.client.iter_messages(channel_identifier, limit=limit):
                message_id = self.save_message_data(message)
                message_count += 1
                
                # Her 10 mesajda bir ilerleme göster
                if message_count % 10 == 0:
                    print(f"   📊 İlerleme: {message_count}/{limit} mesaj")
                
                # Her 50 mesajda bir kısa bekle
                if message_count % 50 == 0:
                    await asyncio.sleep(1)
            
            print(f"\n✅ Kanal çekme tamamlandı!")
            print(f"   📊 Toplam mesaj: {message_count}")
            
            # Analiz raporu oluştur
            self.generate_analysis_report(channel_identifier)
            
        except Exception as e:
            print(f"❌ Kanal çekme hatası: {e}")
    
    def generate_analysis_report(self, channel_name: str = ""):
        """Analiz raporu oluşturur"""
        print(f"\n📊 ANALİZ RAPORU OLUŞTURULUYOR...")
        
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        
        # Temel istatistikler
        cursor.execute("SELECT COUNT(*) FROM messages")
        total_messages = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(DISTINCT ip_address) FROM ip_info")
        total_ips = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(DISTINCT phone_number) FROM phone_numbers")
        total_phones = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(DISTINCT email) FROM emails")
        total_emails = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(DISTINCT sender_id) FROM messages")
        total_senders = cursor.fetchone()[0]
        
        # En çok IP bulunan ülkeler
        cursor.execute('''
            SELECT country, COUNT(*) as count 
            FROM ip_info 
            WHERE country != 'N/A'
            GROUP BY country 
            ORDER BY count DESC 
            LIMIT 10
        ''')
        top_countries = cursor.fetchall()
        
        # En çok mesaj gönderenler
        cursor.execute('''
            SELECT sender_username, sender_first_name, COUNT(*) as count 
            FROM messages 
            WHERE sender_id != 0
            GROUP BY sender_id 
            ORDER BY count DESC 
            LIMIT 10
        ''')
        top_senders = cursor.fetchall()
        
        # En çok geçen IP'ler
        cursor.execute('''
            SELECT ip_address, COUNT(*) as count 
            FROM (
                SELECT json_each.value as ip_address
                FROM messages, json_each(messages.ip_addresses)
            )
            GROUP BY ip_address 
            ORDER BY count DESC 
            LIMIT 10
        ''')
        top_ips = cursor.fetchall()
        
        conn.close()
        
        # Raporu oluştur
        report = self._create_report_text(
            channel_name, total_messages, total_ips, total_phones,
            total_emails, total_senders, top_countries, top_senders, top_ips
        )
        
        # Raporu kaydet
        self._save_report_to_file(report, channel_name)
        
        # Konsola yazdır
        print(report)
    
    def _create_report_text(self, channel_name, total_messages, total_ips,
                           total_phones, total_emails, total_senders,
                           top_countries, top_senders, top_ips) -> str:
        """Rapor metnini oluşturur"""
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        report = f"""
{'='*80}
📊 TELEGRAM DATA SCRAPER - ANALİZ RAPORU
{'='*80}
📅 Oluşturulma Tarihi: {timestamp}
📁 Kanal/Grup: {channel_name or 'Tüm Veriler'}
{'='*80}

📈 GENEL İSTATİSTİKLER:
{'─'*40}
• 📨 Toplam Mesaj: {total_messages}
• 👤 Toplam Gönderen: {total_senders}
• 🌐 Toplam IP Adresi: {total_ips}
• 📱 Toplam Telefon Numarası: {total_phones}
• 📧 Toplam Email Adresi: {total_emails}

🌍 EN ÇOK IP BULUNAN ÜLKELER:
{'─'*40}
"""
        for country, count in top_countries:
            report += f"• {country}: {count} IP\n"
        
        report += f"""
👤 EN AKTİF GÖNDERENLER:
{'─'*40}
"""
        for username, first_name, count in top_senders:
            display_name = username or first_name or "Bilinmeyen"
            report += f"• {display_name}: {count} mesaj\n"
        
        report += f"""
🔢 EN ÇOK GEÇEN IP ADRESLERİ:
{'─'*40}
"""
        for ip, count in top_ips:
            report += f"• {ip}: {count} kez\n"
        
        report += f"""
📁 VERİTABANI BİLGİLERİ:
{'─'*40}
• Veritabanı: {self.db_name}
• Çıktı Dizini: {self.output_dir.absolute()}
• Toplam Boyut: {Path(self.db_name).stat().st_size / 1024:.2f} KB

⚠️ ÖNEMLİ NOTLAR:
{'─'*40}
• Bu script sadece eğitim ve araştırma amaçlıdır
• Telegram'ın kullanım şartlarına uyun
• Kişisel verileri izinsiz toplamayın
• Yerel veri koruma yasalarına uygun kullanın
• Sorumlu kullanım için etik kurallara uyun

{'='*80}
"""
        return report
    
    def _save_report_to_file(self, report: str, channel_name: str):
        """Raporu dosyaya kaydeder"""
        safe_channel_name = re.sub(r'[^\w\-_]', '_', channel_name)[:50]
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        
        filename = f"report_{safe_channel_name}_{timestamp}.txt"
        filepath = self.output_dir / filename
        
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(report)
        
        print(f"📄 Rapor kaydedildi: {filepath}")
    
    def export_to_csv(self):
        """Verileri CSV formatında dışa aktarır"""
        print(f"\n📁 CSV EXPORT BAŞLATILIYOR...")
        
        conn = sqlite3.connect(self.db_name)
        
        # Tüm tabloları export et
        tables = ['messages', 'ip_info', 'phone_numbers', 'emails']
        
        for table in tables:
            try:
                cursor = conn.cursor()
                cursor.execute(f"SELECT * FROM {table}")
                
                filename = f"{table}_{datetime.now().strftime('%Y%m%d')}.csv"
                filepath = self.output_dir / filename
                
                with open(filepath, 'w', newline='', encoding='utf-8') as f:
                    writer = csv.writer(f)
                    
                    # Başlıkları yaz
                    writer.writerow([i[0] for i in cursor.description])
                    
                    # Verileri yaz
                    batch_size = 1000
                    while True:
                        rows = cursor.fetchmany(batch_size)
                        if not rows:
                            break
                        writer.writerows(rows)
                
                print(f"   ✅ {table}: {cursor.rowcount} kayıt -> {filename}")
                
            except Exception as e:
                print(f"   ❌ {table} export hatası: {e}")
        
        conn.close()
        print(f"\n📊 CSV export tamamlandı!")
    
    async def start_client(self) -> bool:
        """Telegram client'ını başlatır"""
        if not self.get_api_credentials():
            return False
        
        try:
            print(f"\n🔌 Telegram'a bağlanılıyor...")
            
            self.client =    async def start_client(self) -> bool:
        """Telegram client'ını başlatır"""
        if not self.get_api_credentials():
            return False
        
        try:
            print(f"\n🔌 Telegram'a bağlanılıyor...")
            
            self.client = TelegramClient(
                self.session_name,
                int(self.api_id),
                self.api_hash
            )
            
            await self.client.start()
            
            # Kullanıcı bilgilerini göster
            me = await self.client.get_me()
            print(f"✅ Bağlantı başarılı!")
            print(f"👤 Giriş yapıldı: {me.first_name} (@{me.username})")
            print(f"🆔 Kullanıcı ID: {me.id}")
            
            return True
            
        except Exception as e:
            print(f"❌ Bağlantı hatası: {e}")
            return False
    
    async def interactive_menu(self):
        """Etkileşimli menüyü gösterir"""
        while True:
            print("\n" + "="*60)
            print("🎮 TELEGRAM DATA SCRAPER - ANA MENÜ")
            print("="*60)
            print("1. Kanal/Grup'tan mesaj çek")
            print("2. Tüm sohbetleri listele")
            print("3. Analiz raporu oluştur")
            print("4. Verileri CSV'ye aktar")
            print("5. IP adresi analiz et (manuel)")
            print("6. Veritabanını temizle")
            print("7. Sistem durumunu göster")
            print("8. Çıkış")
            print("="*60)
            
            choice = input("\nSeçiminiz (1-8): ").strip()
            
            if choice == '1':
                await self._menu_scrape_channel()
            elif choice == '2':
                await self._menu_list_dialogs()
            elif choice == '3':
                self.generate_analysis_report()
            elif choice == '4':
                self.export_to_csv()
            elif choice == '5':
                await self._menu_analyze_ip()
            elif choice == '6':
                self._menu_clear_database()
            elif choice == '7':
                self._menu_show_status()
            elif choice == '8':
                print("\n👋 Çıkış yapılıyor...")
                break
            else:
                print("❌ Geçersiz seçim!")
    
    async def _menu_scrape_channel(self):
        """Kanal çekme menüsü"""
        print("\n📥 KANAL ÇEKME")
        print("-"*40)
        
        channel = input("Kanal/Grup ID veya kullanıcı adı: ").strip()
        if not channel:
            print("❌ Kanal bilgisi gerekli!")
            return
        
        limit = input("Kaç mesaj çekilsin? (varsayılan: 100): ").strip()
        limit = int(limit) if limit.isdigit() else 100
        
        if limit > 10000:
            print("⚠️  Çok yüksek limit! 10000 ile sınırlandırıldı.")
            limit = 10000
        
        await self.scrape_channel(channel, limit)
    
    async def _menu_list_dialogs(self):
        """Sohbetleri listeleme menüsü"""
        print("\n📱 SOHBET LİSTESİ")
        print("-"*40)
        
        try:
            count = 0
            async for dialog in self.client.iter_dialogs():
                count += 1
                print(f"{count:3d}. {dialog.name} (ID: {dialog.id})")
                
                if count % 20 == 0:
                    more = input("\nDevam etmek için Enter, durdurmak için 'q': ")
                    if more.lower() == 'q':
                        break
            
            print(f"\n📊 Toplam sohbet: {count}")
            
        except Exception as e:
            print(f"❌ Sohbet listeleme hatası: {e}")
    
    async def _menu_analyze_ip(self):
        """Manuel IP analiz menüsü"""
        print("\n🌍 MANUEL IP ANALİZİ")
        print("-"*40)
        
        ip = input("Analiz edilecek IP adresi: ").strip()
        if not ip:
            print("❌ IP adresi gerekli!")
            return
        
        geo_data = await self.get_ip_geolocation(ip)
        if geo_data:
            self._save_ip_info(geo_data)
        else:
            print(f"❌ IP analiz edilemedi: {ip}")
    
    def _menu_clear_database(self):
        """Veritabanı temizleme menüsü"""
        print("\n🗑️  VERİTABANI TEMİZLEME")
        print("-"*40)
        
        confirm = input("Tüm veriler silinecek! Emin misiniz? (evet/hayır): ").strip().lower()
        if confirm == 'evet':
            try:
                # Veritabanı dosyasını sil
                db_path = Path(self.db_name)
                if db_path.exists():
                    db_path.unlink()
                    print("✅ Veritabanı silindi!")
                
                # Çıktı dizinini temizle
                for file in self.output_dir.glob("*"):
                    if file.is_file():
                        file.unlink()
                
                # Yeni veritabanı oluştur
                self._setup_database()
                print("✅ Yeni veritabanı oluşturuldu!")
                
            except Exception as e:
                print(f"❌ Temizleme hatası: {e}")
        else:
            print("❌ İşlem iptal edildi.")
    
    def _menu_show_status(self):
        """Sistem durumu menüsü"""
        print("\n📊 SİSTEM DURUMU")
        print("-"*40)
        
        # Veritabanı boyutu
        db_path = Path(self.db_name)
        if db_path.exists():
            size_kb = db_path.stat().st_size / 1024
            print(f"📁 Veritabanı boyutu: {size_kb:.2f} KB")
        else:
            print("📁 Veritabanı: Mevcut değil")
        
        # Tablo istatistikleri
        try:
            conn = sqlite3.connect(self.db_name)
            cursor = conn.cursor()
            
            cursor.execute("SELECT COUNT(*) FROM messages")
            msg_count = cursor.fetchone()[0]
            print(f"📨 Mesaj sayısı: {msg_count}")
            
            cursor.execute("SELECT COUNT(*) FROM ip_info")
            ip_count = cursor.fetchone()[0]
            print(f"🌐 IP kayıt sayısı: {ip_count}")
            
            cursor.execute("SELECT COUNT(*) FROM phone_numbers")
            phone_count = cursor.fetchone()[0]
            print(f"📱 Telefon kayıt sayısı: {phone_count}")
            
            cursor.execute("SELECT COUNT(*) FROM emails")
            email_count = cursor.fetchone()[0]
            print(f"📧 Email kayıt sayısı: {email_count}")
            
            conn.close()
            
        except Exception as e:
            print(f"📊 İstatistik hatası: {e}")
        
        # Çıktı dizini
        csv_files = list(self.output_dir.glob("*.csv"))
        txt_files = list(self.output_dir.glob("*.txt"))
        
        print(f"📁 CSV dosyaları: {len(csv_files)}")
        print(f"📄 Rapor dosyaları: {len(txt_files)}")
        
        # Python versiyonu
        print(f"🐍 Python versiyonu: {sys.version.split()[0]}")
    
    async def run(self):
        """Ana çalıştırma fonksiyonu"""
        print("\n" + "="*60)
        print("🚀 TELEGRAM DATA SCRAPER & IP ANALYZER")
        print("="*60)
        print("Sürüm: 1.0 - 2026")
        print("Termux için optimize edilmiştir")
        print("="*60)
        
        # Termux kontrolü
        try:
            import android
            print("📱 Termux tespit edildi - Android modu aktif")
        except ImportError:
            print("💻 Standart mod - Termux değil")
        
        # Client'ı başlat
        if not await self.start_client():
            print("❌ Telegram bağlantısı kurulamadı!")
            return
        
        # Etkileşimli menüyü başlat
        await self.interactive_menu()
        
        # Client'ı kapat
        await self.client.disconnect()
        print("\n✅ Program başarıyla sonlandırıldı!")
        print("👋 Görüşmek üzere!")

def main():
    """Program giriş noktası"""
    # ASCII banner
    banner = """
    ╔══════════════════════════════════════════════════════╗
    ║      TELEGRAM DATA SCRAPER & IP ANALYZER v1.0        ║
    ║                Termux Optimized                      ║
    ║                 Created: 2026                        ║
    ╚══════════════════════════════════════════════════════╝
    """
    print(banner)
    
    # Ana programı çalıştır
    scraper = TelegramDataScraper()
    
    try:
        # Asenkron fonksiyonu çalıştır
        if sys.platform == 'win32':
            asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
        
        loop = asyncio.get_event_loop()
        loop.run_until_complete(scraper.run())
        
    except KeyboardInterrupt:
        print("\n\n⏹️  Program kullanıcı tarafından durduruldu.")
    except Exception as e:
        print(f"\n❌ Beklenmeyen hata: {e}")
        import traceback
        traceback.print_exc()
    finally:
        print("\n🔚 Program sonlandırıldı.")

if __name__ == "__main__":
    main()
    