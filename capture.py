
import sys
import time
import gi
gi.require_version('Gst', '1.0')
from gi.repository import Gst
from gi.repository import GLib
import numpy as np


Gst.init(None)

class Episode(object):
	GENERIC="generic"
	QR_CODE="qr_code"

	def __init__(self, **kwargs):
		self.episode_id = kwargs['episode_id']
		self.media = kwargs['media']
		self.opened_at = kwargs['opened_at']
		self.updated_at = kwargs['updated_at']
		self.payload = ""
		self.episode_type = kwargs.get('episode_type', Episode.GENERIC)		

		for k,v in kwargs.items():
			setattr(self,k,v)

class Capture(object):
	NTP_EPOCH_DELTA=2208988800
	episodes = []
	episodes_limit = 1000

	def append_episode(episode):
		Capture.episodes.append(episode)
		if len(Capture.episodes) > Capture.episodes_limit:
			Capture.episodes = Capture.episodes[1:]
	
	def update_episode(episode_id, **kwargs):
		"""Update existing episode by episode_id"""
		for ep in Capture.episodes:
			if ep.episode_id == episode_id:
				for k, v in kwargs.items():
					setattr(ep, k, v)
				return ep
		return None

	def __init__(self, spec):
		self.rtsp_url = spec.url
		self.name = spec.name
		self.frame_count = 0
		self.last_log_time = time.time()

	def run(self):
		print(f"[{self.name}] Starting stream capture from {self.rtsp_url}")
		# videoconvert is required to change from I420 to BGR
		# https://gstreamer.freedesktop.org/documentation/rtsp/rtspsrc.html?gi-language=c#rtspsrc:add-reference-timestamp-meta
		gstreamer_cmd = ('rtspsrc name=ingress latency=0 protocols=tcp tcp-timeout=5000000 drop-on-latency=true '
			'add-reference-timestamp-meta=true ! '
			'rtph264depay ! h264parse ! avdec_h264 ! videoconvert ! '
			'video/x-raw, format=(string){BGR, GRAY8}; video/x-bayer,format=(string){rggb,bggr,grbg,gbrg} !'
			'appsink name=egress emit-signals=True sync=False drop=true max-lateness=500000000 max-buffers=4')

		pipeline = Gst.parse_launch(gstreamer_cmd)

		source = pipeline.get_by_name('ingress')
		source.set_property('location', self.rtsp_url)

		sink = pipeline.get_by_name('egress')
		# sink.connect("new-sample", aaa)
		sink.connect("new-sample", self.on_new_sample)

		print(f"[{self.name}] Pipeline created, setting state to PLAYING...")
		loop = GLib.MainLoop()
		pipeline.set_state(Gst.State.PLAYING)
		print(f"[{self.name}] Pipeline state set to PLAYING, waiting for frames...")
		try:
			loop.run()
		except KeyboardInterrupt:
			print(f"[{self.name}] Interrupted by user")
		except Exception as e:
			print(f"[{self.name}] Error in main loop: {e}")
		finally:
			print(f"[{self.name}] Stopping pipeline...")
			pipeline.set_state(Gst.State.NULL)
			print(f"[{self.name}] Pipeline stopped. Total frames processed: {self.frame_count}")

	def on_new_sample(self, appsink):
		sample = appsink.emit("pull-sample")
		if sample:
			buffer = sample.get_buffer()
			caps = sample.get_caps()
			meta = buffer.get_reference_timestamp_meta(None)
			if meta:
				# timestamp/x-ntp
				tsmeta = buffer.get_reference_timestamp_meta(None)
				utc_ns = tsmeta.timestamp - Capture.NTP_EPOCH_DELTA*1e9
				
				height = caps.get_structure(0).get_value('height')
				width = caps.get_structure(0).get_value('width')
				
				img = np.ndarray(
		            (height, width, 3),
		            buffer=buffer.extract_dup(0, buffer.get_size()),
		            dtype=np.uint8)

				self.frame_count += 1
				current_time = time.time()
				# Log frame info every 5 seconds
				if current_time - self.last_log_time >= 5.0:
					print(f"[{self.name}] Processing frame #{self.frame_count}, size: {width}x{height}, timestamp: {utc_ns/1e9:.3f}s")
					self.last_log_time = current_time

				episode = self.process(img, utc_ns)
				if episode:
					Capture.append_episode(episode)
			else:
				# Log when timestamp meta is missing
				if self.frame_count % 100 == 0:
					print(f"[{self.name}] Warning: Frame #{self.frame_count} has no timestamp meta")
		return Gst.FlowReturn.OK

	def process(self, image, timestamp):
		return None

