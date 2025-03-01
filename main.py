#!/usr/bin/env python3
"""
Web Crawler and Text Extractor

This script crawls a specified domain, downloads all HTML pages it finds (without leaving the domain),
and extracts the text content from each page using the HTML text extractor.

Usage:
    python web_crawler_extractor.py <start_url> [output_directory]

If output_directory is not specified, './crawled_data' will be used.

Requirements:
    pip install requests beautifulsoup4 urllib3
"""

import os
import sys
import time
import re
import random
import argparse
from urllib.parse import urlparse, urljoin
from html.parser import HTMLParser
from collections import deque
import threading
import queue

import requests
from bs4 import BeautifulSoup
from requests.exceptions import RequestException


class HTMLTextExtractor(HTMLParser):
    """HTML Parser that extracts text from HTML content."""
    
    def __init__(self):
        super().__init__()
        self.result = []
        self.skip_tags = {'style', 'script', 'meta', 'head', 'title', 'link'}
        self.current_tag = None
    
    def handle_starttag(self, tag, attrs):
        self.current_tag = tag
    
    def handle_endtag(self, tag):
        if tag == self.current_tag:
            self.current_tag = None
    
    def handle_data(self, data):
        if self.current_tag not in self.skip_tags:
            text = data.strip()
            if text:
                self.result.append(text)
    
    def get_text(self):
        return '\n'.join(self.result)


def extract_text_from_html(html_content):
    """
    Extract text from HTML content.
    
    Args:
        html_content (str): HTML content
        
    Returns:
        str: Extracted text
    """
    parser = HTMLTextExtractor()
    parser.feed(html_content)
    return parser.get_text()


class WebCrawler:
    """Web crawler that extracts text from all pages in a domain."""
    
    def __init__(self, start_url, output_dir, num_threads=5, delay=1.0):
        """
        Initialize the web crawler.
        
        Args:
            start_url (str): The starting URL to crawl
            output_dir (str): Directory to save the extracted text
            num_threads (int): Number of crawler threads
            delay (float): Delay between requests to the same domain (seconds)
        """
        self.start_url = start_url
        self.output_dir = output_dir
        self.num_threads = num_threads
        self.delay = delay
        
        # Parse the domain from the start URL
        parsed_url = urlparse(start_url)
        self.domain = parsed_url.netloc
        
        # Create directories for HTML and text
        self.html_dir = os.path.join(output_dir, 'html')
        self.text_dir = os.path.join(output_dir, 'text')
        
        os.makedirs(self.html_dir, exist_ok=True)
        os.makedirs(self.text_dir, exist_ok=True)
        
        # Set for tracking visited URLs
        self.visited_urls = set()
        self.url_queue = queue.Queue()
        
        # Add the start URL to the queue
        self.url_queue.put(start_url)
        self.visited_urls.add(start_url)
        
        # Create a lock for thread safety
        self.lock = threading.Lock()
        
        # Statistics
        self.processed_count = 0
        self.failed_count = 0
        
        # User agent list for rotating
        self.user_agents = [
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.1.1 Safari/605.1.15',
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:89.0) Gecko/20100101 Firefox/89.0',
            'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/92.0.4515.107 Safari/537.36'
        ]
    
    def get_safe_filename(self, url):
        """Convert a URL to a safe filename."""
        # Remove the protocol and domain
        parsed_url = urlparse(url)
        path = parsed_url.path
        
        # Handle the path
        if not path or path == '/':
            path = '/index'
        
        # Replace unsafe characters
        safe_name = re.sub(r'[^a-zA-Z0-9_-]', '_', path)
        
        # Add query parameters (encoded) if they exist
        if parsed_url.query:
            query_hash = abs(hash(parsed_url.query)) % 10000
            safe_name += f'_query_{query_hash}'
        
        # Ensure the filename isn't too long
        if len(safe_name) > 200:
            safe_name = safe_name[:190] + f'_hash_{abs(hash(url)) % 10000}'
        
        return safe_name + '.txt'
    
    def is_valid_url(self, url):
        """Check if the URL is valid and belongs to the target domain."""
        try:
            # Parse the URL
            parsed_url = urlparse(url)
            
            # Check if the URL has the same domain
            if parsed_url.netloc != self.domain:
                return False
            
            # Check if the URL scheme is http or https
            if parsed_url.scheme not in ['http', 'https']:
                return False
            
            # Avoid common non-HTML resources
            path = parsed_url.path.lower()
            if any(path.endswith(ext) for ext in ['.jpg', '.jpeg', '.png', '.gif', '.pdf', 
                                                   '.zip', '.tar', '.gz', '.mp3', '.mp4', 
                                                   '.avi', '.mov', '.css', '.js']):
                return False
            
            return True
        except:
            return False
    
    def extract_links(self, url, html_content):
        """Extract all links from the HTML content."""
        links = set()
        try:
            soup = BeautifulSoup(html_content, 'html.parser')
            for a_tag in soup.find_all('a', href=True):
                link = a_tag['href']
                
                # Convert relative URLs to absolute URLs
                absolute_link = urljoin(url, link)
                
                # Check if the URL is valid
                if self.is_valid_url(absolute_link):
                    links.add(absolute_link)
        except Exception as e:
            print(f"Error extracting links from {url}: {e}")
        
        return links
    
    def process_url(self, url):
        """Process a single URL: download, save HTML, extract text, and find links."""
        try:
            # Add a small random delay to be polite
            time.sleep(self.delay * (0.5 + random.random()))
            
            # Rotate user agents
            headers = {
                'User-Agent': random.choice(self.user_agents),
                'Accept': 'text/html,application/xhtml+xml,application/xml',
                'Accept-Language': 'en-US,en;q=0.9',
                'Connection': 'keep-alive'
            }
            
            # Download the page
            response = requests.get(url, headers=headers, timeout=10)
            
            # Check if the response is HTML
            content_type = response.headers.get('Content-Type', '').lower()
            if 'text/html' not in content_type:
                print(f"Skipping non-HTML content at {url} (Content-Type: {content_type})")
                return
            
            # Get the HTML content
            html_content = response.text
            
            # Generate safe filenames
            safe_name = self.get_safe_filename(url)
            html_filename = os.path.join(self.html_dir, safe_name.replace('.txt', '.html'))
            text_filename = os.path.join(self.text_dir, safe_name)
            
            # Save the HTML file
            with open(html_filename, 'w', encoding='utf-8') as f:
                f.write(html_content)
            
            # Extract and save the text
            extracted_text = extract_text_from_html(html_content)
            with open(text_filename, 'w', encoding='utf-8') as f:
                f.write(extracted_text)
            
            # Extract links
            links = self.extract_links(url, html_content)
            
            # Add new links to the queue
            with self.lock:
                for link in links:
                    if link not in self.visited_urls:
                        self.url_queue.put(link)
                        self.visited_urls.add(link)
                
                # Update statistics
                self.processed_count += 1
                
                # Print progress
                if self.processed_count % 10 == 0 or self.processed_count < 10:
                    print(f"Processed: {self.processed_count} | Queue: {self.url_queue.qsize()} | Failed: {self.failed_count}")
            
            print(f"Processed: {url} -> {text_filename}")
                
        except RequestException as e:
            with self.lock:
                self.failed_count += 1
            print(f"Request error for {url}: {e}")
        except Exception as e:
            with self.lock:
                self.failed_count += 1
            print(f"Error processing {url}: {e}")
    
    def worker(self):
        """Worker thread that processes URLs from the queue."""
        while True:
            try:
                # Get a URL from the queue with a timeout
                url = self.url_queue.get(timeout=2)
                
                # Process the URL
                self.process_url(url)
                
                # Mark the task as done
                self.url_queue.task_done()
            except queue.Empty:
                # No more URLs in the queue for the timeout period
                # Check if other threads are still working
                with self.lock:
                    if self.url_queue.empty():
                        break
            except Exception as e:
                print(f"Worker error: {e}")
    
    def crawl(self):
        """Start the crawling process with multiple threads."""
        print(f"Starting crawler with {self.num_threads} threads")
        print(f"Domain: {self.domain}")
        print(f"Output directories: {self.html_dir} and {self.text_dir}")
        
        # Create and start worker threads
        threads = []
        for i in range(self.num_threads):
            thread = threading.Thread(target=self.worker)
            thread.daemon = True
            thread.start()
            threads.append(thread)
        
        # Wait for all threads to finish
        for thread in threads:
            thread.join()
        
        print("\nCrawling completed!")
        print(f"Total pages processed: {self.processed_count}")
        print(f"Failed requests: {self.failed_count}")
        print(f"HTML saved to: {self.html_dir}")
        print(f"Extracted text saved to: {self.text_dir}")


def main():
    parser = argparse.ArgumentParser(description='Web Crawler and Text Extractor')
    parser.add_argument('start_url', help='The starting URL to crawl')
    parser.add_argument('--output-dir', '-o', default='./crawled_data', 
                        help='Directory to save the extracted text (default: ./crawled_data)')
    parser.add_argument('--threads', '-t', type=int, default=5,
                        help='Number of crawler threads (default: 5)')
    parser.add_argument('--delay', '-d', type=float, default=1.0,
                        help='Delay between requests to the same domain in seconds (default: 1.0)')
    
    args = parser.parse_args()
    
    # Validate the URL
    try:
        parsed_url = urlparse(args.start_url)
        if not parsed_url.scheme or not parsed_url.netloc:
            raise ValueError("Invalid URL format")
    except Exception:
        print(f"Error: Invalid URL '{args.start_url}'", file=sys.stderr)
        sys.exit(1)
    
    # Create the output directory if it doesn't exist
    if not os.path.exists(args.output_dir):
        os.makedirs(args.output_dir)
    
    # Create and run the crawler
    crawler = WebCrawler(args.start_url, args.output_dir, args.threads, args.delay)
    crawler.crawl()


if __name__ == "__main__":
    main()