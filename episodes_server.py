from http.server import BaseHTTPRequestHandler
from http.server import ThreadingHTTPServer
import json
from urllib.parse import urlparse, parse_qs
from datetime import datetime
import time

class HttpGetHandler(BaseHTTPRequestHandler):
	API_PREFIX = "/vision/api/v3"

	def do_GET(self):
		parsed_path = urlparse(self.path)
		path = parsed_path.path

		if not path.startswith(self.API_PREFIX):
			self.send_response(404)
			self.end_headers()
			return

		# Remove prefix to get the actual endpoint
		endpoint = path[len(self.API_PREFIX):]

		if endpoint == "/episodes":
			self.handle_episodes(parsed_path)
		elif endpoint == "/streams":
			self.handle_streams()
		elif endpoint == "/monitoring/liveness":
			self.handle_liveness()
		else:
			self.send_response(404)
			self.end_headers()

	def handle_episodes(self, parsed_path):
		query = parse_qs(parsed_path.query)

		self.send_response(200)
		self.send_header("Content-type", "application/json")
		self.end_headers()
		poll_timeout = None
		if 'poll_timeout' in query and query['poll_timeout']:
			poll_timeout = int(query['poll_timeout'][0])

		updated_at_gt = 0
		if 'updated_at_gt' in query and query['updated_at_gt']:
			updated_at_gt = int(query['updated_at_gt'][0])
		t1 = datetime.now()

		episodes = []
		if poll_timeout:
			while True:
				episodes = self.get_episodes(updated_at_gt)
				t2 = datetime.now()
				if (t2-t1).seconds >= poll_timeout:
					break
				if len(episodes) > 0:
					break
				time.sleep(1)
		else:
			episodes = self.get_episodes(updated_at_gt)
		
		# episodes_list schema: collection_response + episodes array
		response_data = {
			'estimated_count': len(episodes),
			'episodes': episodes
		}
		response = json.dumps(response_data, default=vars)+"\n"
		self.wfile.write(response.encode())

	def handle_streams(self):
		self.send_response(200)
		self.send_header("Content-type", "application/json")
		self.end_headers()
		
		streams = []
		if HttpGetHandler.manager:
			for stream in HttpGetHandler.manager.streams:
				if not stream.to_delete:
					# stream_config schema: at minimum requires 'name'
					streams.append({
						'name': stream.name
					})
		
		# streams_list schema: collection_response + openmetrics_labels + streams array
		response_data = {
			'estimated_count': len(streams),
			'streams': streams
		}
		response = json.dumps(response_data)+"\n"
		self.wfile.write(response.encode())

	def handle_liveness(self):
		self.send_response(200)
		self.send_header("Content-type", "application/json")
		self.end_headers()
		
		# vision_server_info schema
		now_ms = int(time.time() * 1000)
		started_at = HttpGetHandler.started_at  # already in seconds (utc)
		
		response_data = {
			'server_version': HttpGetHandler.server_version,
			'build': HttpGetHandler.build,
			'now': now_ms,
			'started_at': started_at
		}
		
		response = json.dumps(response_data)+"\n"
		self.wfile.write(response.encode())

	def get_episodes(self, updated_at_gt):
		return [e for e in HttpGetHandler.episodes if e.updated_at > updated_at_gt]



def run_http(episodes, port, manager=None, server_version="1.0.0", build=1, server_class=ThreadingHTTPServer, handler_class=HttpGetHandler):
	HttpGetHandler.episodes = episodes
	HttpGetHandler.manager = manager
	HttpGetHandler.server_version = server_version
	HttpGetHandler.build = build
	HttpGetHandler.started_at = int(time.time())
	server_address = ('', port)
	httpd = server_class(server_address, handler_class)
	try:
		httpd.serve_forever()
	except KeyboardInterrupt:
		httpd.server_close()
