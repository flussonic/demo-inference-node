import threading

from capture import Capture
import time
import urllib3
import json
import hashlib
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
	
	def get_url(self):
		"""Get the URL for this stream"""
		return self.url
	
	def config_matches(self, config):
		"""Check if the given config matches this stream's configuration"""
		config_url = None
		if 'inputs' in config and len(config['inputs']) > 0:
			config_url = config['inputs'][0]['url']
		elif 'url' in config:
			config_url = config['url']
		return config_url == self.url


class Manager(object):

	def __init__(self, config_external_url):
		super().__init__()
		print(f"[Manager] Initializing with config_external_url: {config_external_url}")
		self.api_token = None
		self.config_external_url = self._parse_url(config_external_url)
		print(f"[Manager] Parsed URL: {self.config_external_url}, API token: {'***' if self.api_token else 'None'}")
		self.streams = []
		self.last_config_hash = None
		self.last_status_log_time = time.time()

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
			print(f"[Manager] Fetching config from config_external: {url}")
			
			r = http.request('GET', url, headers=headers, timeout=5.0)
			
			if r.status != 200:
				print(f"[Manager] Error: HTTP {r.status}, response: {r.data.decode('utf-8', errors='ignore')[:200]}")
				return
			
			response_text = r.data.decode('utf-8')
			
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
			
			# Calculate config hash to detect changes
			config_hash = hashlib.md5(response_text.encode()).hexdigest()
			
			# Log config details only when config changes or on first fetch
			if self.last_config_hash is None:
				print(f"[Manager] Initial config fetched: {len(config['streams'])} stream(s)")
				print(f"[Manager] Config content: {response_text[:500]}")
			elif config_hash != self.last_config_hash:
				print(f"[Manager] Config changed: {len(config['streams'])} stream(s)")
				print(f"[Manager] Config content: {response_text[:500]}")
			else:
				# Log brief status on each successful fetch (but less frequently)
				current_time = time.time()
				if current_time - self.last_status_log_time >= 10.0:
					active_streams = [s.name for s in self.streams if not s.to_delete]
					print(f"[Manager] Config OK: {len(config['streams'])} stream(s) in config, {len(active_streams)} active")
					self.last_status_log_time = current_time
			
			self.last_config_hash = config_hash
			
			for s in self.streams:
				s.to_delete = True
			for n in config['streams']:
				stream_name = n['name']
				found_existing = False
				for o in self.streams:
					if stream_name == o.name:
						o.to_delete = False
						found_existing = True
						# Check if configuration changed (e.g., URL changed)
						if not o.config_matches(n):
							print(f"[Manager] Configuration changed for stream: {stream_name}, restarting...")
							# Stop old capture
							if o.capture:
								try:
									o.capture.stop()
								except Exception as e:
									print(f"[Manager] Error stopping capture for {stream_name}: {e}")
							# Wait a bit for thread to finish
							if o.thread and o.thread.is_alive():
								o.thread.join(timeout=2.0)
							# Create new capture with new config
							try:
								# Update stream URL
								if 'inputs' in n and len(n['inputs']) > 0:
									o.url = n['inputs'][0]['url']
								elif 'url' in n:
									o.url = n['url']
								# Launch new capture
								o.capture = self.launch(o)
								o.thread = threading.Thread(target=o.capture.run, args=())
								o.thread.start()
								print(f"[Manager] Restarted stream: {stream_name} with new configuration")
							except Exception as e:
								print(f"[Manager] Error restarting stream {stream_name}: {e}")
								import traceback
								traceback.print_exc()
						break
				
				if not found_existing:
					# New stream - create it
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

			# Remove deleted streams
			for o in self.streams:
				if o.to_delete:
					print(f"[Manager] Delete old stream: {o.name}")
					if o.capture:
						try:
							o.capture.stop()
						except Exception as e:
							print(f"[Manager] Error stopping capture for {o.name}: {e}")
					if o.thread and o.thread.is_alive():
						o.thread.join(timeout=2.0)
			self.streams = [o for o in self.streams if not o.to_delete]
		except Exception as e:
			print(f"[Manager] Exception in reconfigure: {type(e).__name__}: {e}")
			import traceback
			traceback.print_exc()


	def launch(self, spec):
		return Capture(spec)

