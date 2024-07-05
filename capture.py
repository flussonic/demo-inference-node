#!/usr/bin/env python3

import sys
import time
import gi
gi.require_version('Gst', '1.0')
from gi.repository import Gst
from gi.repository import GLib
import datetime as dt
import numpy as np
import cv2

detector = cv2.QRCodeDetector()
qr_codes = {}


Gst.init(None)

NTP_EPOCH_DELTA=2208988800

streamLink = ""


# videoconvert is required to change from I420 to BGR
# https://gstreamer.freedesktop.org/documentation/rtsp/rtspsrc.html?gi-language=c#rtspsrc:add-reference-timestamp-meta
gstreamer_cmd = ('rtspsrc name=m_rtspsrc latency=0 protocols=tcp tcp-timeout=5000000 drop-on-latency=true '
	'add-reference-timestamp-meta=true ! '
	'rtph264depay ! h264parse ! avdec_h264 ! videoconvert ! '
	'video/x-raw, format=(string){BGR, GRAY8}; video/x-bayer,format=(string){rggb,bggr,grbg,gbrg} !'
	'appsink name=sink emit-signals=True sync=False drop=true max-lateness=500000000 max-buffers=4')

pipeline = Gst.parse_launch(gstreamer_cmd)








def on_new_sample(appsink):
	sample = appsink.emit("pull-sample")
	if sample:
		buffer = sample.get_buffer()
		caps = sample.get_caps()
		meta = buffer.get_reference_timestamp_meta(None)
		if meta:
			# timestamp/x-ntp
			tsmeta = buffer.get_reference_timestamp_meta(None)
			ntp = tsmeta.timestamp
			d = dt.datetime.fromtimestamp(ntp/1e9 - NTP_EPOCH_DELTA, tz=dt.UTC)
			# print("Timestamp:", d)
			img = np.ndarray(
	            (caps.get_structure(0).get_value('height'),
	             caps.get_structure(0).get_value('width'),
	             3),
	            buffer=buffer.extract_dup(0, buffer.get_size()),
	            dtype=np.uint8)

			data, bbox, _ = detector.detectAndDecode(img)
			print("%s - %s - %s" % (d,data,bbox))
			if data and data not in qr_codes:
				qr_codes[data] = (data, d)
				print(data,d)
	return Gst.FlowReturn.OK


source = pipeline.get_by_name('m_rtspsrc')
source.set_property('location', streamLink)

sink = pipeline.get_by_name('sink')
sink.connect("new-sample", on_new_sample)



loop = GLib.MainLoop()
pipeline.set_state(Gst.State.PLAYING)
try:
    loop.run()
except:
    pass

pipeline.set_state(Gst.State.NULL)
