from http.server import BaseHTTPRequestHandler
from http.server import ThreadingHTTPServer
import json
from urllib.parse import urlparse, parse_qs
from datetime import datetime
import time


class HttpGetHandler(BaseHTTPRequestHandler):
	def do_GET(self):
		parsed_path = urlparse(self.path)
		query = parse_qs(parsed_path.query)

		self.send_response(200)
		self.send_header("Content-type", "application/json")
		self.end_headers()
		poll_timeout = None
		if query['poll_timeout']:
			poll_timeout = int(query['poll_timeout'][0])

		updated_at_gt = None
		if query['updated_at_gt']:
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
		response = json.dumps({'episodes': episodes}, default=vars)+"\n"
		self.wfile.write(response.encode())

	def get_episodes(self, updated_at_gt):
		return [e for e in HttpGetHandler.episodes if e.updated_at > updated_at_gt]



def run_http(episodes, port, server_class=ThreadingHTTPServer, handler_class=HttpGetHandler):
	HttpGetHandler.episodes = episodes
	server_address = ('', port)
	httpd = server_class(server_address, handler_class)
	try:
		httpd.serve_forever()
	except KeyboardInterrupt:
		httpd.server_close()
