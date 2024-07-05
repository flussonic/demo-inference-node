import threading

from capture import Capture
import time
import urllib3
import json


class Stream(object):
	def __init__(self, config):
		self.name = config['name']
		self.url = config['url']
		self.thread = None
		self.capture = None
		self.to_delete = False


class Manager(object):

	def __init__(self, config_external_url):
		super().__init__()
		self.config_external_url = config_external_url
		self.streams = []


	def run(self):

		while True:
			self.reconfigure()
			time.sleep(3)

	def reconfigure(self):
		http = urllib3.PoolManager()
		r = http.request('GET', self.config_external_url+"/streams")
		config = json.loads(r.data.decode('utf-8'))
		for s in self.streams:
			s.to_delete = True
		for n in config['streams']:
			is_new = True
			for o in self.streams:
				if n['name'] == o.name:
					o.to_delete = False
					is_new = False
					# TODO: reconfiguration of capture
			if is_new:
				stream = Stream(n)
				stream.capture = self.launch(stream)
				stream.thread = threading.Thread(target=stream.capture.run, args=())
				self.streams.append(stream)
				stream.thread.start()
				print("Launch new",stream)

		for o in self.streams:
			if o.to_delete:
				print("Delete old", o)
				stream.thread.stop()
		self.streams = [o for o in self.streams if not o.to_delete]


	def launch(self, spec):
		return Capture(spec)

