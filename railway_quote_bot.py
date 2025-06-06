#!/usr/bin/env python3
"""
Railway Twitter Quote Bot
Updated version with tracking and no quote formatting
"""

import os
import json
import random
import logging
from datetime import datetime
import tweepy
import gspread
from google.oauth2.service_account import Credentials

# Set up logging for Railway
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger(__name__)

class RailwayQuoteBot:
    def __init__(self):
        """Initialize the Railway Quote Bot"""
        self.setup_twitter()
        self.setup_google_sheets()
        
    def setup_twitter(self):
        """Initialize Twitter API connection"""
        try:
            self.twitter_client = tweepy.Client(
                bearer_token=os.getenv('TWITTER_BEARER_TOKEN'),
                consumer_key=os.getenv('TWITTER_CONSUMER_KEY'),
                consumer_secret=os.getenv('TWITTER_CONSUMER_SECRET'),
                access_token=os.getenv('TWITTER_ACCESS_TOKEN'),
                access_token_secret=os.getenv('TWITTER_ACCESS_TOKEN_SECRET'),
                wait_on_rate_limit=True
            )
            
            # Test connection
            me = self.twitter_client.get_me()
            logger.info(f"Twitter API connected successfully! User: @{me.data.username}")
            
        except Exception as e:
            logger.error(f"Twitter API connection failed: {str(e)}")
            raise
    
    def setup_google_sheets(self):
        """Initialize Google Sheets API connection"""
        try:
            # Get service account info from environment variable
            service_account_json = os.getenv('GOOGLE_SERVICE_ACCOUNT_JSON')
            if not service_account_json:
                raise ValueError("GOOGLE_SERVICE_ACCOUNT_JSON environment variable not set")
            
            # Parse JSON and create credentials
            service_account_info = json.loads(service_account_json)
            scopes = [
                'https://www.googleapis.com/auth/spreadsheets',
                'https://www.googleapis.com/auth/drive'
            ]
            
            credentials = Credentials.from_service_account_info(
                service_account_info, 
                scopes=scopes
            )
            
            # Initialize Google Sheets client
            self.gc = gspread.authorize(credentials)
            
            # Open spreadsheet
            sheets_id = os.getenv('GOOGLE_SHEETS_ID')
            worksheet_name = os.getenv('GOOGLE_WORKSHEET_NAME', 'Sheet1')
            
            self.sheet = self.gc.open_by_key(sheets_id)
            self.worksheet = self.sheet.worksheet(worksheet_name)
            
            logger.info("Google Sheets API connected successfully!")
            
        except Exception as e:
            logger.error(f"Google Sheets API connection failed: {str(e)}")
            raise
    
    def get_quotes_from_sheet(self):
        """Fetch all quotes from Google Sheets"""
        try:
            all_records = self.worksheet.get_all_records()
            
            quotes = []
            for idx, row in enumerate(all_records):
                quote_text = None
                author = None
                posted = False
                
                # Look for quote text in common column names
                for key in ['Quote', 'Text', 'Content', 'Message', 'quote', 'text']:
                    if key in row and row[key]:
                        quote_text = str(row[key]).strip()
                        break
                
                # Look for author in common column names
                for key in ['Author', 'By', 'Source', 'author', 'by']:
                    if key in row and row[key]:
                        author = str(row[key]).strip()
                        break
                
                # Check if already posted
                for key in ['Posted', 'Tweeted', 'Used', 'posted', 'tweeted', 'used']:
                    if key in row and str(row[key]).lower() in ['yes', 'true', '1', 'posted', 'tweeted']:
                        posted = True
                        break
                
                if quote_text:
                    quotes.append({
                        'text': quote_text,
                        'author': author,
                        'row_index': idx + 2,  # +2 because sheets are 1-indexed and we skip header
                        'posted': posted
                    })
            
            logger.info(f"Successfully fetched {len(quotes)} quotes from Google Sheets")
            return quotes
            
        except Exception as e:
            logger.error(f"Error fetching quotes: {str(e)}")
            return []
    
    def mark_as_posted(self, row_index):
        """Mark quote as posted in the sheet"""
        try:
            # Try to find or create a 'Posted' column
            headers = self.worksheet.row_values(1)
            posted_col = None
            
            # Look for existing posted column
            for i, header in enumerate(headers):
                if header.lower() in ['posted', 'tweeted', 'used']:
                    posted_col = i + 1
                    break
            
            # If no posted column exists, create one
            if posted_col is None:
                posted_col = len(headers) + 1
                self.worksheet.update_cell(1, posted_col, 'Posted')
            
            # Mark as posted
            self.worksheet.update_cell(row_index, posted_col, 'Yes')
            logger.info(f"Marked row {row_index} as posted")
            
        except Exception as e:
            logger.error(f"Error marking quote as posted: {str(e)}")
    
    def format_tweet(self, quote_data):
        """Format quote into tweet (no quotes, just text)"""
        quote_text = quote_data['text']
        author = quote_data.get('author')
        
        # Start with just the text (no quotes)
        tweet = quote_text
        
        # Add author if available
        if author:
            tweet += f' - {author}'
        
        # Ensure tweet fits Twitter's 280 character limit
        if len(tweet) > 280:
            max_quote_length = 280 - len(' - ') - len(author or '')
            if max_quote_length > 50:
                quote_text = quote_text[:max_quote_length-3] + '...'
                tweet = quote_text
                if author:
                    tweet += f' - {author}'
        
        return tweet
    
    def post_quote(self):
        """Main function to select and post a quote"""
        try:
            logger.info("Starting quote posting process...")
            
            # Get quotes from Google Sheets
            quotes = self.get_quotes_from_sheet()
            
            if not quotes:
                logger.error("No quotes found in Google Sheets!")
                return False
            
            # Filter unposted quotes
            unposted_quotes = [q for q in quotes if not q['posted']]
            
            if not unposted_quotes:
                logger.warning("All quotes have been posted! Consider adding more quotes.")
                # Fall back to random quote from all quotes
                selected_quote = random.choice(quotes)
            else:
                selected_quote = random.choice(unposted_quotes)
            
            logger.info(f"Selected quote: {selected_quote['text'][:50]}...")
            
            # Format tweet
            tweet_text = self.format_tweet(selected_quote)
            
            # Post to Twitter
            response = self.twitter_client.create_tweet(text=tweet_text)
            
            if response.data:
                tweet_id = response.data['id']
                logger.info(f"Tweet posted successfully!")
                logger.info(f"Tweet ID: {tweet_id}")
                logger.info(f"Tweet content: {tweet_text}")
                
                # Mark as posted in sheet
                self.mark_as_posted(selected_quote['row_index'])
                
                return True
            else:
                logger.error("Failed to post tweet - no response data")
                return False
                
        except Exception as e:
            logger.error(f"Error posting quote: {str(e)}")
            return False

def main():
    """Main function for Railway execution"""
    try:
        logger.info("=== Railway Quote Bot Starting ===")
        logger.info(f"Execution time: {datetime.now()}")
        
        # Initialize and run bot
        bot = RailwayQuoteBot()
        success = bot.post_quote()
        
        if success:
            logger.info("=== Bot execution completed successfully! ===")
        else:
            logger.error("=== Bot execution failed ===")
            exit(1)
            
    except Exception as e:
        logger.error(f"Bot crashed: {str(e)}")
        exit(1)

if __name__ == "__main__":
    main()
