
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

	def __init__(self, **kwargs):
		self.episode_id = kwargs['episode_id']
		self.meta = kwargs['media']
		self.opened_at = kwargs['opened_at']
		self.updated_at = kwargs['updated_at']
		self.payload = ""
		self.episode_type = Episode.GENERIC		

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
		

	def __init__(self, rtsp_url):
		self.rtsp_url = rtsp_url


	def run(self):
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


		loop = GLib.MainLoop()
		pipeline.set_state(Gst.State.PLAYING)
		try:
			loop.run()
		except:
		    pass

		pipeline.set_state(Gst.State.NULL)




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
				img = np.ndarray(
		            (caps.get_structure(0).get_value('height'),
		             caps.get_structure(0).get_value('width'),
		             3),
		            buffer=buffer.extract_dup(0, buffer.get_size()),
		            dtype=np.uint8)

				episode = self.process(img, utc_ns)
				if episode:
					Capture.append_episode(episode)
		return Gst.FlowReturn.OK

	def process(self, image, timestamp):
		return None

