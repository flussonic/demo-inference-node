import threading

from capture import Capture
import time
import urllib3
import json
from urllib.parse import urlparse, urlunparse, ParseResult


class Stream(object):
	def __init__(self, config):
		self.name = config['name']
		# Extract URL from inputs[*].url structure
		if 'inputs' in config and len(config['inputs']) > 0:
			self.url = config['inputs'][0]['url']
		elif 'url' in config:
			# Fallback for backward compatibility
			self.url = config['url']
		else:
			raise ValueError(f"Stream {config.get('name', 'unknown')} has no URL in inputs or url field")
		self.thread = None
		self.capture = None
		self.to_delete = False


class Manager(object):

	def __init__(self, config_external_url):
		super().__init__()
		print(f"[Manager] Initializing with config_external_url: {config_external_url}")
		self.api_token = None
		self.config_external_url = self._parse_url(config_external_url)
		print(f"[Manager] Parsed URL: {self.config_external_url}, API token: {'***' if self.api_token else 'None'}")
		self.streams = []

	def _parse_url(self, url):
		"""Parse URL and extract API token from user@host format"""
		parsed = urlparse(url)
		if parsed.username:
			# Extract token from username part
			self.api_token = parsed.username
			# Reconstruct URL without username
			netloc = parsed.hostname
			if parsed.port:
				netloc = f"{netloc}:{parsed.port}"
			new_parsed = ParseResult(
				scheme=parsed.scheme,
				netloc=netloc,
				path=parsed.path,
				params=parsed.params,
				query=parsed.query,
				fragment=parsed.fragment
			)
			return urlunparse(new_parsed)
		return url

	def run(self):

		while True:
			self.reconfigure()
			time.sleep(3)

	def reconfigure(self):
		try:
			http = urllib3.PoolManager()
			headers = {}
			if self.api_token:
				headers['Authorization'] = f'Bearer {self.api_token}'
			
			url = self.config_external_url + "/streams"
			print(f"[Manager] Fetching config from {url}")
			
			r = http.request('GET', url, headers=headers, timeout=5.0)
			
			print(f"[Manager] Response status: {r.status}, headers: {dict(r.headers)}")
			
			if r.status != 200:
				print(f"[Manager] Error: HTTP {r.status}, response: {r.data.decode('utf-8', errors='ignore')[:200]}")
				return
			
			response_text = r.data.decode('utf-8')
			print(f"[Manager] Response body (first 500 chars): {response_text[:500]}")
			
			try:
				config = json.loads(response_text)
			except json.JSONDecodeError as e:
				print(f"[Manager] JSON decode error: {e}, response: {response_text[:500]}")
				return
			
			if config is None:
				print(f"[Manager] Error: config is None")
				return
			
			if 'streams' not in config:
				print(f"[Manager] Error: 'streams' key not found in config. Keys: {list(config.keys()) if isinstance(config, dict) else 'not a dict'}")
				return
			
			if not isinstance(config['streams'], list):
				print(f"[Manager] Error: 'streams' is not a list, type: {type(config['streams'])}")
				return
			
			print(f"[Manager] Found {len(config['streams'])} stream(s) in config")
			
			for s in self.streams:
				s.to_delete = True
			for n in config['streams']:
				is_new = True
				for o in self.streams:
					if n['name'] == o.name:
						o.to_delete = False
						is_new = False
				if is_new:
					try:
						stream = Stream(n)
						stream.capture = self.launch(stream)
						stream.thread = threading.Thread(target=stream.capture.run, args=())
						self.streams.append(stream)
						stream.thread.start()
						print(f"[Manager] Launch new stream: {stream.name}")
					except Exception as e:
						print(f"[Manager] Error launching stream {n.get('name', 'unknown')}: {e}")
						import traceback
						traceback.print_exc()

			for o in self.streams:
				if o.to_delete:
					print(f"[Manager] Delete old stream: {o.name}")
					if o.thread and o.thread.is_alive():
						# Note: Python threads don't have stop(), we'll let them finish naturally
						pass
			self.streams = [o for o in self.streams if not o.to_delete]
		except Exception as e:
			print(f"[Manager] Exception in reconfigure: {type(e).__name__}: {e}")
			import traceback
			traceback.print_exc()


	def launch(self, spec):
		return Capture(spec)

