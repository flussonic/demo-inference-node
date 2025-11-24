
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
		self.should_stop = False
		self.loop = None
		self.pipeline = None

	def run(self):
		print(f"[{self.name}] Capture started for stream: {self.name}, RTSP URL: {self.rtsp_url}")
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
		self.loop = GLib.MainLoop()
		self.pipeline = pipeline
		
		# Set pipeline to PLAYING and wait for state change
		ret = pipeline.set_state(Gst.State.PLAYING)
		if ret == Gst.StateChangeReturn.FAILURE:
			print(f"[{self.name}] ERROR: Failed to set pipeline to PLAYING state")
			return
		elif ret == Gst.StateChangeReturn.ASYNC:
			# Wait for state change to complete
			ret = pipeline.get_state(timeout=Gst.SECOND * 5)
			if ret[0] == Gst.StateChangeReturn.FAILURE:
				print(f"[{self.name}] ERROR: Pipeline failed to transition to PLAYING state")
				return
			elif ret[0] == Gst.StateChangeReturn.TIMEOUT:
				print(f"[{self.name}] WARNING: Pipeline state change timed out")
			else:
				state_name = "NULL" if ret[1] == Gst.State.NULL else "READY" if ret[1] == Gst.State.READY else "PLAYING" if ret[1] == Gst.State.PLAYING else "PAUSED"
				print(f"[{self.name}] Pipeline state: {state_name}")
		
		print(f"[{self.name}] Pipeline state set to PLAYING, waiting for frames...")
		try:
			self.loop.run()
		except KeyboardInterrupt:
			print(f"[{self.name}] Interrupted by user")
		except Exception as e:
			print(f"[{self.name}] Error in main loop: {e}")
		finally:
			print(f"[{self.name}] Stopping pipeline...")
			if self.pipeline:
				self.pipeline.set_state(Gst.State.NULL)
			print(f"[{self.name}] Pipeline stopped. Total frames processed: {self.frame_count}")

	def stop(self):
		"""Stop the capture gracefully"""
		print(f"[{self.name}] Stop requested")
		self.should_stop = True
		if self.loop:
			self.loop.quit()

	def on_new_sample(self, appsink):
		if self.should_stop:
			return Gst.FlowReturn.FLUSHING
		sample = appsink.emit("pull-sample")
		if sample:
			buffer = sample.get_buffer()
			caps = sample.get_caps()
			meta = buffer.get_reference_timestamp_meta(None)
			
			# Extract image dimensions and data
			height = caps.get_structure(0).get_value('height')
			width = caps.get_structure(0).get_value('width')
			
			img = np.ndarray(
	            (height, width, 3),
	            buffer=buffer.extract_dup(0, buffer.get_size()),
	            dtype=np.uint8)

			# Get timestamp - use meta if available, otherwise use current time
			if meta:
				# timestamp/x-ntp
				tsmeta = buffer.get_reference_timestamp_meta(None)
				utc_ns = tsmeta.timestamp - Capture.NTP_EPOCH_DELTA*1e9
			else:
				# Fallback to current time if no timestamp meta
				utc_ns = int(time.time() * 1e9)
				# Log when timestamp meta is missing (but less frequently)
				if self.frame_count == 0:
					print(f"[{self.name}] Warning: First frame has no timestamp meta, using current time")
				elif self.frame_count % 100 == 0:
					print(f"[{self.name}] Warning: Frame #{self.frame_count} has no timestamp meta, using current time")

			self.frame_count += 1
			current_time = time.time()
			# Log frame info every 5 seconds
			if current_time - self.last_log_time >= 5.0:
				print(f"[{self.name}] Processing frame #{self.frame_count}, size: {width}x{height}, timestamp: {utc_ns/1e9:.3f}s")
				self.last_log_time = current_time

			# Process frame regardless of timestamp meta presence
			episode = self.process(img, utc_ns)
			if episode:
				Capture.append_episode(episode)
		else:
			# Log when sample is None (should not happen often)
			if self.frame_count == 0:
				print(f"[{self.name}] Warning: Received None sample on first attempt")
		return Gst.FlowReturn.OK

	def process(self, image, timestamp):
		return None

